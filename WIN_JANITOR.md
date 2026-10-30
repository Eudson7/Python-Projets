# Win Janitor

Programa para **limpar lixos do Windows** e **encontrar arquivos grandes** que você
pode escolher para excluir. Interface escura em 3 passos, operação em lote com
confirmação e log de tudo.

O repositório é apenas o armazenamento do código: o programa roda no seu PC.

## Requisitos

- Windows 10/11
- **Python 3.12** (o seu 3.12.7 serve) com Tk — vem junto no instalador padrão
- Dependência: `customtkinter` (ver `requirements.txt`)

## Como rodar

```bat
py -3.12 -m pip install -r requirements.txt
py -3.12 -m win_janitor
```

Isso abre a interface. Sem argumentos, o módulo abre a GUI; com argumentos, usa o
terminal:

```bat
py -3.12 -m win_janitor scan            :: só mostra o que dá para limpar (nada apaga)
py -3.12 -m win_janitor clean --dry-run :: simula a limpeza
py -3.12 -m win_janitor clean --yes     :: limpa sem perguntar
py -3.12 -m win_janitor bigfiles --min-mb 800
```

## Os 3 passos da interface

1. **Limpeza** — lista as categorias (Temp, Windows Update, dumps, cache de
   navegador, miniaturas, logs), com o tamanho de cada uma. Você marca o que
   quer, clica em *Limpar* e confirma. Nada fora da lista é tocado.
2. **Arquivos grandes** — varre as unidades marcadas (menos as pastas de
   sistema) e lista os arquivos acima do tamanho mínimo com **nome, tipo,
   tamanho e data de criação**. Você marca e escolhe excluir — por padrão é
   exclusão permanente; ligue *Mover para a lixeira* se preferir.
3. **Relatório** — o que aconteceu nesta sessão e os logs gravados.

## Regras de segurança (não negociáveis)

- Allowlist: só o que está em `win_janitor/targets.py` é alvo. Não existe lista
  de proibidos que precise ser mantida à mão.
- `win_janitor/safety.py` barra `..`, variáveis não resolvidas, `System32`,
  `Program Files`, `Windows` inteiro e as pastas pessoais
  (Documentos, Downloads, Área de Trabalho, Imagens, Músicas, Vídeos, OneDrive).
- A varredura não segue junction/symlink de pasta — impossível escapar da pasta
  autorizada.
- Arquivo em uso é **pulado**, nunca derruba a limpeza.
- Toda operação gera um log JSON em
  `%LOCALAPPDATA%\win_janitor\logs\`.

## Testes

```bat
py -3.12 -m pip install -r requirements-dev.txt
py -3.12 -m pytest tests -q
```

29 testes cobrindo segurança de caminhos, varredura, limpeza, arquivos travados,
modo simulação, filtros de arquivos grandes, exclusão e logs.

## Gerar o .exe

```bat
build.bat
```

O executável sai em `dist\WinJanitor\WinJanitor.exe` (pasta única — copie a
pasta `WinJanitor` inteira). O PyInstaller precisa rodar no seu PC, com o
Python 3.12.

## Estrutura

```
win_janitor/
  targets.py    allowlist de alvos de limpeza
  safety.py     validação de caminhos e áreas protegidas
  scan.py       varredura de lixo (somente leitura)
  clean.py      remoção, lixeira do Windows e consolidação
  bigfiles.py   varredura de arquivos grandes com progresso/cancelamento
  report.py     logs JSON
  cli.py        versão de terminal
  ui/           interface (tema escuro, janela de confirmação, 3 passos)
tests/          pytest
win_janitor.spec, build.bat, run_win_janitor.py   empacotamento
```
