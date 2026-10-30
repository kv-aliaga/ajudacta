# 🔧 AjudACTA

Painel desktop para configurar o perfil AWS `default` e acompanhar serviços do ACTA, que sustentam o ciclo PDCA (*Plan, Do, Check, Act*).

## 📌 Visão geral

O AjudACTA reúne em uma interface Windows consultas à AWS, ao cluster Kubernetes e às APIs do ACTA. O aplicativo também oferece ações operacionais: atualizar credenciais temporárias, emitir tokens Firebase por meio de um projeto local, reiniciar uma API e reconstruir a infraestrutura gerenciada pelo checkout local do `acta-platform`.

As telas dependem de ferramentas e arquivos externos específicos. Abrir o aplicativo não executa um rollout ou uma reconstrução; essas ações são iniciadas nas respectivas telas.

## ✨ Capacidades

| Área | Capacidades |
| --- | --- |
| Perfil AWS | Recebe um bloco INI `[default]`, atualiza `~/.aws/credentials` e `~/.aws/config`, valida a identidade pelo STS e restaura o conteúdo anterior se a validação falhar. |
| APIs do cluster | Localiza o Elastic IP pela tag `Name=acta-prod-k3s`, monta URLs públicas e consulta os endpoints HTTP das sete APIs configuradas no código. |
| Token IDs | Lê uma lista local de Firebase UIDs, chama um script local de emissão, mostra metadados e expiração do JWT e grava um histórico CSV. |
| Diagnóstico | Reúne identidade AWS, disponibilidade HTTP, Deployments, sincronização de `InfisicalSecret`, aplicação Argo CD e certificados; pode abrir o Argo CD por um túnel local e enviar a tabela ao Codex CLI para análise. |
| Rollout APIs | Inspeciona um Deployment por vez, acompanha seu rollout e permite reinício após confirmação e verificações de acesso, réplicas e Secrets. Também pode solicitar a inclusão do IP público atual no security group para acesso à API Kubernetes. |
| Terminal de logs | Acompanha os logs dos Deployments com `kubectl logs --follow` e oculta linhas de probes HTTP 200 reconhecidas pelo filtro. |
| Reconstrução | Confere AWS e o state Terraform do `acta-platform`, gera um plano de destruição para revisão e, após confirmação, aplica o plano e chama `deploy.ps1`. Permite retomar apenas a implantação se a destruição já terminou na mesma sessão. |

As verificações HTTP indicam a resposta de cada URL consultada. Elas não substituem a inspeção da prontidão dos pods nem comprovam a saúde de todas as dependências da API.

## 🛠️ Tecnologias

| Tecnologia | Uso |
| --- | --- |
| Python | Aplicativo desktop e automação local. |
| Tkinter e CustomTkinter 6.0.0 | Interface gráfica; a versão de CustomTkinter está fixada em [`requirements.txt`](requirements.txt). |
| Boto3 1.43.111 | Consultas e operações AWS. |
| `markdown-it-py` 4.2.0 e `tkinterweb` 4.25.5 | Exibição de conteúdo Markdown na interface. |
| `winotify` 1.1.0 | Notificações do Windows. |
| AWS CLI, `kubectl` e Terraform | Ferramentas externas usadas pelas telas operacionais. |
| PowerShell, Git, GitHub CLI e SSH | Ferramentas exigidas pelo fluxo de reconstrução. |
| Codex CLI | Análise opcional da tabela de diagnóstico. |

## ✅ Pré-requisitos e configuração

- Windows com Python 3.10 ou superior e Tkinter disponível. O código usa sintaxe introduzida no Python 3.10; não há uma versão de Python fixada pelo projeto.
- Credenciais AWS temporárias autorizadas para o ambiente ACTA, com `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token` e região. As permissões AWS e Kubernetes necessárias variam conforme a tela e a ação.
- Para consultas ao cluster, `kubectl` no `PATH` e o kubeconfig ACTA existente em `~/.kube/acta-aws.yaml`. O aplicativo usa o namespace `acta-prod` para as APIs e `argocd` para o Argo CD.
- Para a tela **Token IDs**, copie `integrations/token-id/.env.example` para `integrations/token-id/.env`, configure a `FIREBASE_WEB_API_KEY` e coloque `firebase-service-account.json` e `firebaseuid_validos.csv` nessa pasta. O script `fb.py` já faz parte deste repositório; `firebase-id-token.csv` será criado ali como histórico local.
- Para **Matar e implantar**, inicialize o submódulo [`acta-platform`](https://github.com/AppActa/acta-platform) em `integrations/acta-platform`. Forneça `infra/aws/terraform.tfstate` e `infra/aws/terraform.tfvars` nesse checkout, além da chave `~/.aws/labsuser.pem` e AWS CLI, Terraform, `kubectl`, SSH, `gh`, Git e PowerShell no `PATH`.

Os caminhos do `acta-platform` e do `token-id` são calculados a partir da raiz deste projeto em [`aws_profile_app/constants.py`](aws_profile_app/constants.py). O diagnóstico também consulta o procedimento [`ROLLOUT_SESSION.md`](ROLLOUT_SESSION.md) deste repositório. O kubeconfig continua sendo um arquivo local em `~/.kube/acta-aws.yaml`.

Para carregar as credenciais Universal Auth do Infisical na confirmação da reconstrução, crie um `.env` local na raiz deste repositório:

```env
CLIENT_ID=<client-id-do-ambiente>
CLIENT_SECRET=<client-secret-do-ambiente>
```

Os arquivos `.env`, a service account, o CSV de UIDs, o histórico de tokens, o state e o tfvars são ignorados pelo Git. Eles precisam ser configurados localmente após um clone. Não copie seus valores para commits, issues ou logs compartilhados.

## 🚀 Execução local

Clone com o submódulo ou, se o repositório já estiver clonado, inicialize-o antes de executar o aplicativo:

```powershell
git clone --recurse-submodules https://github.com/kv-aliaga/ajudacta.git
# Dentro de um clone existente:
git submodule update --init --recursive
```

No PowerShell, a partir da raiz do repositório:

```powershell
$VenvPath = Join-Path $env:LOCALAPPDATA 'ajudacta-venv'
python -m venv $VenvPath
& (Join-Path $VenvPath 'Scripts\Activate.ps1')
python -m pip install -r requirements.txt
python aws_profile_setup.pyw
```

A primeira tela recebe o bloco `[default]` das credenciais temporárias. Confira a região e selecione a atualização do perfil. O aplicativo grava os arquivos em `~/.aws` e consulta o STS para confirmar a identidade; em caso de falha, tenta restaurar o conteúdo anterior. Não cole esse bloco em arquivos versionados.

As consultas às APIs e ao Kubernetes exigem que o perfil `default` e o acesso ao cluster estejam válidos no momento da operação. A tela **Diagnóstico** reúne as verificações antes de um rollout. A análise pelo Codex CLI é opcional e requer o CLI instalado e autenticado.

## ⚠️ Operações com efeito no ambiente

**Rollout APIs** reinicia somente o Deployment selecionado, após confirmação na interface. Antes da ação, o aplicativo valida o perfil AWS, o acesso Kubernetes, a capacidade saudável e as condições de Secrets; depois acompanha o rollout e inspeciona o estado final. O botão **Liberar meu IP em 6443** pode adicionar uma regra `/32` ao security group da instância encontrada pela tag ACTA, também após confirmação.

**Matar e implantar** é uma operação destrutiva. A tela exige um state Terraform local, prepara um plano `-destroy` e mostra os recursos previstos antes da confirmação. Ao prosseguir, aplica o plano de destruição salvo e executa `deploy.ps1` do checkout configurado. Revise conta, região, checkout e todos os recursos do plano. Se a implantação falhar após a destruição, a infraestrutura pode ficar parcial; a retomada sem nova destruição só é oferecida enquanto a sessão do aplicativo preserva esse estado.

**Token IDs** mostra o token Firebase na tela e o grava em texto no `firebase-id-token.csv` local. Trate esse arquivo e a área de transferência como material sensível. A abertura do Argo CD também pode mostrar sua senha inicial no terminal do diagnóstico, se o Secret correspondente ainda existir.

## 📁 Estrutura

```text
.
├── aws_profile_setup.pyw           # entrada do aplicativo
├── aws_profile_app/
│   ├── application.py              # janela e navegação
│   ├── constants.py                # caminhos e nomes dos serviços
│   ├── profile_config.py           # atualização e validação do perfil AWS
│   ├── features/                  # telas e operações
│   └── ui/                        # componentes de interface
├── integrations/
│   ├── acta-platform/             # submódulo Git, fixado em um commit
│   └── token-id/fb.py             # emissor Firebase; dados locais ignorados
├── requirements.txt               # dependências Python fixadas
└── ROLLOUT_SESSION.md             # procedimento operacional separado
```

O [`ROLLOUT_SESSION.md`](ROLLOUT_SESSION.md) descreve um procedimento manual específico para rollouts. Confira o escopo e as condições desse documento antes de usá-lo; ele não é um passo necessário para iniciar a interface.

## 🤝 Links e autoria

- [Repositório](https://github.com/kv-aliaga/ajudacta) · `acta.institutojef@gmail.com`
- Integrações: [acta-platform](https://github.com/AppActa/acta-platform).
- Contribuições: use *issues* e *pull requests*.
