import json
import shutil
from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIGURAÇÃO
# ============================================================

PASTA_ORIGEM = Path(
    r"C:\Users\Elias\OneDrive\Área de Trabalho\Documentos\LEAKMAP Edge\06_fpga\resultados"
)

PASTA_DESTINO = PASTA_ORIGEM / "unicos"

ARQUIVO_RELATORIO = PASTA_ORIGEM / "relatorio_duplicados.txt"


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def data_modificacao(arquivo):
    timestamp = arquivo.stat().st_mtime

    return datetime.fromtimestamp(timestamp).strftime(
        "%d/%m/%Y %H:%M:%S"
    )


def gerar_assinatura_json(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        return json.dumps(
            dados,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":")
        )

    except (json.JSONDecodeError, UnicodeDecodeError) as erro:
        print(f"[ERRO] JSON inválido: {caminho.name}")
        print(f"       {erro}")
        return None


# ============================================================
# ANALISAR JSONS
# ============================================================

def analisar_jsons():

    grupos = {}

    arquivos = [
        arquivo
        for arquivo in PASTA_ORIGEM.glob("*.json")
        if arquivo.is_file()
    ]

    print(f"Arquivos encontrados: {len(arquivos)}")
    print()

    for arquivo in arquivos:

        assinatura = gerar_assinatura_json(arquivo)

        if assinatura is None:
            continue

        if assinatura not in grupos:
            grupos[assinatura] = []

        grupos[assinatura].append(arquivo)

    return grupos


# ============================================================
# SELECIONAR MAIS RECENTES
# ============================================================

def selecionar_mais_recentes(grupos):

    selecionados = []
    duplicados = []

    for arquivos in grupos.values():

        arquivos.sort(
            key=lambda arquivo: arquivo.stat().st_mtime,
            reverse=True
        )

        arquivo_mais_recente = arquivos[0]

        selecionados.append(arquivo_mais_recente)

        if len(arquivos) > 1:

            duplicados.append({
                "mantido": arquivo_mais_recente,
                "descartados": arquivos[1:]
            })

    return selecionados, duplicados


# ============================================================
# COPIAR ARQUIVOS ÚNICOS
# ============================================================

def copiar_unicos(arquivos):

    PASTA_DESTINO.mkdir(parents=True, exist_ok=True)

    for arquivo in arquivos:

        destino = PASTA_DESTINO / arquivo.name

        contador = 1

        while destino.exists():

            destino = (
                PASTA_DESTINO
                / f"{arquivo.stem}_{contador}{arquivo.suffix}"
            )

            contador += 1

        shutil.copy2(arquivo, destino)

        print(f"[COPIADO] {arquivo.name}")


# ============================================================
# GERAR RELATÓRIO
# ============================================================

def gerar_relatorio(
    total_analisados,
    total_unicos,
    duplicados
):

    total_duplicados = sum(
        len(grupo["descartados"])
        for grupo in duplicados
    )

    linhas = []

    linhas.append("=" * 70)
    linhas.append("RELATÓRIO DE ANÁLISE DE JSONS")
    linhas.append("=" * 70)
    linhas.append("")

    linhas.append(
        f"Data da análise: "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )

    linhas.append("")

    linhas.append(
        f"Arquivos analisados : {total_analisados}"
    )

    linhas.append(
        f"Arquivos únicos     : {total_unicos}"
    )

    linhas.append(
        f"Arquivos duplicados : {total_duplicados}"
    )

    linhas.append("")
    linhas.append("=" * 70)

    if not duplicados:

        linhas.append("NENHUM DUPLICADO ENCONTRADO.")
        linhas.append("")

    else:

        linhas.append("DUPLICADOS ENCONTRADOS")
        linhas.append("=" * 70)
        linhas.append("")

        for numero, grupo in enumerate(duplicados, start=1):

            mantido = grupo["mantido"]
            descartados = grupo["descartados"]

            linhas.append(f"GRUPO {numero}")
            linhas.append("-" * 70)

            linhas.append("ARQUIVO MANTIDO (MAIS RECENTE):")

            linhas.append(
                f"  {mantido.name}"
            )

            linhas.append(
                f"  Modificado: {data_modificacao(mantido)}"
            )

            linhas.append("")

            linhas.append("ARQUIVOS DUPLICADOS DESCARTADOS:")

            for arquivo in descartados:

                linhas.append(
                    f"  {arquivo.name}"
                )

                linhas.append(
                    f"  Modificado: {data_modificacao(arquivo)}"
                )

                linhas.append("")

            linhas.append("=" * 70)
            linhas.append("")

    linhas.append("RESUMO")
    linhas.append("=" * 70)

    linhas.append(
        f"Total analisado : {total_analisados}"
    )

    linhas.append(
        f"Total único     : {total_unicos}"
    )

    linhas.append(
        f"Total duplicado : {total_duplicados}"
    )

    linhas.append("")

    linhas.append(
        "Arquivos únicos salvos em:"
    )

    linhas.append(
        str(PASTA_DESTINO)
    )

    texto = "\n".join(linhas)

    with open(
        ARQUIVO_RELATORIO,
        "w",
        encoding="utf-8"
    ) as arquivo:

        arquivo.write(texto)

    return texto


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("ANÁLISE DE JSONS DUPLICADOS")
    print("=" * 70)
    print()

    if not PASTA_ORIGEM.exists():

        print("[ERRO] A pasta de origem não existe:")
        print(PASTA_ORIGEM)

        return

    grupos = analisar_jsons()

    total_analisados = sum(
        len(arquivos)
        for arquivos in grupos.values()
    )

    arquivos_unicos, duplicados = selecionar_mais_recentes(
        grupos
    )

    copiar_unicos(arquivos_unicos)

    gerar_relatorio(
        total_analisados,
        len(arquivos_unicos),
        duplicados
    )

    print()
    print("=" * 70)
    print("DUPLICADOS ENCONTRADOS")
    print("=" * 70)
    print()

    if not duplicados:

        print("Nenhum duplicado encontrado.")

    else:

        for numero, grupo in enumerate(
            duplicados,
            start=1
        ):

            mantido = grupo["mantido"]

            print(f"GRUPO {numero}")
            print()

            print(
                f"  [MANTIDO] {mantido.name}"
            )

            print(
                f"            {data_modificacao(mantido)}"
            )

            for arquivo in grupo["descartados"]:

                print(
                    f"  [DESCARTADO] {arquivo.name}"
                )

                print(
                    f"               {data_modificacao(arquivo)}"
                )

            print()

    total_duplicados = sum(
        len(grupo["descartados"])
        for grupo in duplicados
    )

    print("=" * 70)
    print("CONCLUÍDO")
    print("=" * 70)
    print()

    print(f"Arquivos analisados : {total_analisados}")
    print(f"Arquivos únicos     : {len(arquivos_unicos)}")
    print(f"Arquivos duplicados : {total_duplicados}")

    print()
    print("Únicos salvos em:")
    print(PASTA_DESTINO)

    print()
    print("Relatório salvo em:")
    print(ARQUIVO_RELATORIO)
    print()


if __name__ == "__main__":
    main()
