"""LEAKMAP - historico dos eventos da bancada.

Cada evento fica com a verdade da simulacao ao lado (servida so no perfil de
demonstracao) e com o sinal em alta resolucao em volta dele.

Onde fica, pelo endereco em LEAKMAP_BANCO (ou DATABASE_URL, o nome que o
Render usa):
  postgresql://...   PostgreSQL: sobrevive a reinicios e publicacoes. E o que
                     o dashboard do operador precisa na nuvem.
  caminho de arquivo SQLite local (vem com o Python)
  vazio              SQLite em memoria: some quando o servico reinicia.

O mesmo SQL nos dois bancos. Numa conexao com o PostgreSQL que caiu (banco
gerenciado costuma derrubar conexao parada), a operacao reconecta e tenta de
novo uma vez.
"""
import json
import sqlite3
import threading

# "eventos": os alertas de vazamento; "sobrepressoes": os alertas de sobrepressao, a parte
TABELAS = ('eventos', 'sobrepressoes')
CRIAR = ('CREATE TABLE IF NOT EXISTS {t} (id TEXT PRIMARY KEY, instante_utc TEXT, linha TEXT, nivel TEXT, '
         'evento TEXT, verdade TEXT, sinal TEXT)')
INDICE = 'CREATE INDEX IF NOT EXISTS {t}_por_instante ON {t} (instante_utc)'
GRAVAR = ('INSERT INTO {t} (id, instante_utc, linha, nivel, evento, verdade, sinal) '
          'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET instante_utc = excluded.instante_utc, '
          'linha = excluded.linha, nivel = excluded.nivel, evento = excluded.evento, verdade = excluded.verdade, '
          'sinal = excluded.sinal')


def e_postgres(endereco):
    return str(endereco or '').startswith(('postgres://', 'postgresql://'))


class Historico:
    def __init__(self, endereco=':memory:'):
        self.endereco = endereco or ':memory:'
        self.postgres = e_postgres(self.endereco)
        self._trava = threading.Lock()
        self._db = None
        self._conectar()
        for t in TABELAS:
            self._executar(CRIAR.format(t=t))
            self._executar(INDICE.format(t=t))

    @property
    def tipo(self):
        return 'postgresql' if self.postgres else ('sqlite em memoria' if self.endereco == ':memory:' else 'sqlite')

    def _conectar(self):
        if self.postgres:
            import psycopg
            self._db = psycopg.connect(self.endereco, autocommit=True, connect_timeout=15)
        else:
            self._db = sqlite3.connect(self.endereco, check_same_thread=False, isolation_level=None)

    def _executar(self, sql, parametros=(), buscar=None):
        if self.postgres:
            sql = sql.replace('?', '%s')
        with self._trava:
            for tentativa in (1, 2):
                try:
                    cursor = self._db.cursor()
                    cursor.execute(sql, parametros)
                    if buscar == 'um':
                        return cursor.fetchone()
                    if buscar == 'todos':
                        return cursor.fetchall()
                    return None
                except Exception as erro:
                    if not self.postgres or tentativa == 2 or not _conexao_caiu(erro):
                        raise
                    self._conectar()

    def gravar(self, evento, verdade, sinal, tabela='eventos'):
        self._executar(GRAVAR.format(t=_tabela(tabela)), (evento['id'], evento['instante_utc'], evento['linha'], evento['nivel'],
                                json.dumps(evento, ensure_ascii=False), json.dumps(verdade, ensure_ascii=False),
                                json.dumps(sinal)))

    def listar(self, desde=None, nivel=None, linha=None, limite=50, tabela='eventos'):
        sql, par = 'SELECT evento, verdade FROM %s WHERE 1=1' % _tabela(tabela), []
        if desde:
            sql, par = sql + ' AND instante_utc >= ?', par + [desde]
        if nivel:
            sql, par = sql + ' AND nivel = ?', par + [nivel]
        if linha:
            sql, par = sql + ' AND linha = ?', par + [linha]
        sql, par = sql + ' ORDER BY instante_utc DESC LIMIT ?', par + [int(limite)]
        return [{'evento': json.loads(e), 'verdade': json.loads(v)} for e, v in self._executar(sql, par, 'todos')]

    def obter(self, ident):
        r = self._executar('SELECT evento, verdade FROM eventos WHERE id = ?', (ident,), 'um')
        return None if r is None else {'evento': json.loads(r[0]), 'verdade': json.loads(r[1])}

    def sinal(self, ident):
        r = self._executar('SELECT sinal FROM eventos WHERE id = ?', (ident,), 'um')
        return None if r is None else json.loads(r[0])

    def contar(self, tabela='eventos'):
        return int(self._executar('SELECT COUNT(*) FROM %s' % _tabela(tabela), (), 'um')[0])

    def fechar(self):
        with self._trava:
            self._db.close()


def _tabela(nome):
    if nome not in TABELAS:
        raise ValueError('tabela desconhecida: %s' % nome)
    return nome


def _conexao_caiu(erro):
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(erro, (psycopg.OperationalError, psycopg.InterfaceError))
