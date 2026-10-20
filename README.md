# ArcOS

Launcher de aplicativos Android em Python, para rodar no **Termux**. Cada app ganha um código numerado; você abre digitando o código, depois de se autenticar com uma senha que não aparece na tela.

```
╔══════════════════════════════╗
║  ArcOS Terminal v0.1.0       ║
╚══════════════════════════════╝
arc-os > list
Autorização (senha):
[01] Discord
[02] Spotify
arc-os ● > open 02
Abrindo Spotify...
```

Só usa a biblioteca padrão do Python (3.8+). Nenhuma dependência, sem root.

## Instalar (no Termux)

```sh
# copie a pasta arc-os para o celular, entre nela e rode:
sh install.sh
arc-os help
```

Sem instalar: dentro da pasta, `python -m arcos help`.

## Primeiros passos

```sh
arc-os shell                 # abre o terminal do ArcOS (pede para criar a senha no 1º uso)
```

Dentro do shell (ou como `arc-os <comando>` direto):

```
add com.discord --name Discord --alias dc
add com.spotify.music --name Spotify
list
open 01        # ou: open dc
```

O nome do pacote de um app aparece na URL dele na Play Store (`...details?id=com.discord`).

## Comandos

| Comando | Função |
|---|---|
| `list` | Lista os apps (`-v` mostra o pacote) |
| `open <código\|alias>` | Abre o app |
| `search <texto>` | Procura por nome, alias ou pacote |
| `info <código>` | Detalhes de um app |
| `add <pacote> [--name N] [--alias A] [--activity X]` | Cadastra |
| `remove <código> [-y]` | Remove (o código fica livre) |
| `alias <código> <nome>` | Apelido (`-` remove) |
| `scan [--import]` | Tenta descobrir apps instalados (precisa de ADB; senão use `add`) |
| `auth` / `lock` / `passwd` | Autenticar, encerrar sessão, trocar senha |
| `status` | Sessão, senha, apps, ambiente |
| `history [-n N]` | Histórico de comandos |
| `shell` | Terminal interativo (`exit` sai e encerra a sessão) |
| `bash` | Sai para o shell real do Termux (pede senha) |
| `config [get\|set\|reset]` | Configurações (`session_timeout`, `max_attempts`, `lockout_seconds`, `theme`, `prompt`, `banner`, `history_limit`) |
| `theme [nome]` | `red`, `green`, `blue`, `purple`, `amber`, `mono` |
| `boot install\|remove\|status` | Inicialização automática |
| `doctor` | Verifica a instalação |
| `version`, `help [comando]` | |

**Protegidos por senha:** `list`, `open`, `search`, `info`, `add`, `remove`, `alias`, `scan`, `history`, `bash`, `boot`, `config set/reset`. A senha vale por 5 minutos (`session_timeout`) e a cada comando protegido a validade é renovada. Depois de 5 senhas erradas, bloqueia por 60 s.

## Abrir o Termux sozinho ao ligar o celular

```sh
arc-os boot install            # shell do ArcOS abre ao abrir o Termux
arc-os boot install --kiosk    # o Termux abre direto no ArcOS (usa exec)
```

No modo kiosk, o `exit` fecha o Termux; para voltar ao shell normal, use o comando `bash` (pede senha). Para desfazer: `arc-os boot remove`.

Para o **Termux abrir sozinho no boot** (e não só ao abrir o app):

1. Instale o app **Termux:Boot** (mesma origem do Termux: F-Droid ou GitHub) e abra-o uma vez.
2. Dê ao Termux a permissão **Exibir sobre outros apps**.
3. Tire o Termux da otimização de bateria.

O `boot install` cria `~/.termux/boot/arc-os-boot.sh` (acorda o Termux) e um trecho marcado no `~/.bashrc` (inicia o `arc-os shell`).

## Esconder os ícones

O ArcOS não esconde ícones: isso é do launcher. No Samsung (One UI): *Configurações da tela inicial → Ocultar apps* (ou longo-toque na tela inicial → Configurações). Apps ocultos continuam abrindo normalmente via `open`.

## Segurança: o que ela é e o que não é

É uma **trava de conveniência/privacidade**, não um cofre:

- A senha é guardada com PBKDF2-SHA256 (200 mil iterações, salt aleatório) em `~/.arc-os/` com permissão 600; nunca em texto puro nem no histórico.
- Quem tiver o celular desbloqueado ainda abre os apps pela gaveta do Android, pelas Configurações ou pela busca. O ArcOS só protege o *caminho do ArcOS*.
- Para proteger de verdade, combine com: bloqueio de tela forte, **Pasta Segura** (Samsung) ou **Perfil de trabalho/Ilha**, e o bloqueio por app.

## Como o app é aberto

Em ordem, até um funcionar: `am start -n pacote/activity` (se você passou `--activity`), `am start` por pacote + categoria LAUNCHER, `monkey -p pacote`, e `cmd package resolve-activity`. Se algum app específico não abrir, rode `arc-os doctor` e tente cadastrar com `--activity` (a activity aparece em `adb shell cmd package resolve-activity --brief <pacote>`).

Digitando dentro do Termux (que está em primeiro plano) o Android permite abrir os apps normalmente. Já abrir o Termux a partir do boot depende da permissão "Exibir sobre outros apps".

## Estrutura

```
arc-os/
├── arcos/              (o import não aceita hífen: o pacote é "arcos"; o comando é "arc-os")
│   ├── cli.py          comandos, parser e shell interativo
│   ├── auth.py         senha, sessão e bloqueio
│   ├── apps.py         abertura dos apps e scan
│   ├── database.py     códigos -> pacotes (apps.json)
│   ├── config.py       configurações e gravação atômica
│   ├── logger.py       histórico
│   ├── boot.py         autostart (Termux:Boot e ~/.bashrc)
│   └── ui.py           cores e temas
├── tests/test_arcos.py
├── install.sh
└── pyproject.toml
```

Dados do usuário ficam em `~/.arc-os/` (troque com a variável `ARCOS_HOME`). Para testar fora do Android sem abrir nada: `ARCOS_DRY_RUN=1`.

```sh
python -m unittest discover -s tests
```
