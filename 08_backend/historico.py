"""LEAKMAP - historico dos eventos da bancada, em SQLite (vem com o Python).

Cada evento fica com a verdade da simulacao ao lado (servida so no perfil de
demonstracao) e com o sinal em alta resolucao em volta dele. O arquivo do
banco vem de LEAKMAP_BANCO; sem ela, fica em memoria e some ao reiniciar,
como acontece de qualquer jeito no disco do plano gratuito do Render.
"""
import json
import sqlite3
import threading


class Historico:
    def __init__(self, caminho=':memory:'):
        self._trava = threading.Lock()
        self._db = sqlite3.connect(caminho, check_same_thread=False)
        self._db.execute('CREATE TABLE IF NOT EXISTS eventos (id TEXT PRIMARY KEY, instante_utc TEXT, linha TEXT, '
                         'nivel TEXT, evento TEXT, verdade TEXT, sinal TEXT)')
        self._db.commit()

    def gravar(self, evento, verdade, sinal):
        with self._trava:
            self._db.execute('INSERT OR REPLACE INTO eventos VALUES (?, ?, ?, ?, ?, ?, ?)',
                             (evento['id'], evento['instante_utc'], evento['linha'], evento['nivel'],
                              json.dumps(evento, ensure_ascii=False), json.dumps(verdade, ensure_ascii=False),
                              json.dumps(sinal)))
            self._db.commit()

    def listar(self, desde=None, nivel=None, linha=None, limite=50):
        sql, par = 'SELECT evento, verdade FROM eventos WHERE 1=1', []
        if desde:
            sql, par = sql + ' AND instante_utc >= ?', par + [desde]
        if nivel:
            sql, par = sql + ' AND nivel = ?', par + [nivel]
        if linha:
            sql, par = sql + ' AND linha = ?', par + [linha]
        sql, par = sql + ' ORDER BY instante_utc DESC LIMIT ?', par + [int(limite)]
        with self._trava:
            linhas = self._db.execute(sql, par).fetchall()
        return [{'evento': json.loads(e), 'verdade': json.loads(v)} for e, v in linhas]

    def obter(self, ident):
        with self._trava:
            r = self._db.execute('SELECT evento, verdade FROM eventos WHERE id = ?', (ident,)).fetchone()
        return None if r is None else {'evento': json.loads(r[0]), 'verdade': json.loads(r[1])}

    def sinal(self, ident):
        with self._trava:
            r = self._db.execute('SELECT sinal FROM eventos WHERE id = ?', (ident,)).fetchone()
        return None if r is None else json.loads(r[0])

    def fechar(self):
        with self._trava:
            self._db.close()
