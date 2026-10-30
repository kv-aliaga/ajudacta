# Sessão de rollout das APIs ACTA

Use estas instruções para verificar e executar, de forma individual e sequencial, os rollouts autorizados das APIs ACTA. Esta sessão não altera código, manifests, Secrets nem infraestrutura. Não recrie o cluster, não provisione recursos e não altere regras de rede.

## Regras de segurança e escopo

- Use exclusivamente o perfil AWS `default`, com as credenciais temporárias da sessão ativa do AWS Academy/Vocareum.
- Nunca mostre, registre, copie para arquivos de saída ou salve em logs, terminal ou Git access keys, session tokens, senhas ou valores de Secrets. Não leia nem imprima valores de Secrets do Kubernetes ou Infisical.
- Não procure credenciais em outros perfis, arquivos, histórico de shell ou fontes alternativas. Se as credenciais estiverem ausentes/expiradas, pare e solicite ao usuário uma nova sessão AWS Academy/Vocareum.
- Antes de qualquer operação, valide a identidade e a região AWS. Se a conta ou região não corresponder ao alvo esperado, pare e informe isso.
- Use somente o cluster ACTA existente, o kubeconfig abaixo e o namespace `acta-prod`. Se Kubernetes rejeitar a autenticação ou o acesso, informe o erro observado e pare. Não contorne o bloqueio.
- A sessão é exclusivamente para verificar e executar rollouts previamente autorizados. Não execute ações destrutivas nem altere recursos fora dos rollouts explicitamente autorizados.
- Uma instância EC2 em estado `running` não prova que o Kubernetes, o Argo CD ou os Deployments estejam saudáveis.

## Preparação no PowerShell (Windows)

Abra PowerShell. Não habilite transcrição (`Start-Transcript`) durante esta sessão.

```powershell
$env:AWS_PROFILE = 'default'
$Kubeconfig = Join-Path $HOME '.kube\acta-aws.yaml'

# Deve retornar uma identidade válida para a sessão temporária ativa.
aws sts get-caller-identity --profile default

# Leia a região configurada; não invente uma região.
$Region = aws configure get region --profile default
if (-not $Region) { throw 'O perfil default não tem região configurada. Pare e peça orientação.' }
Write-Output "Região ativa: $Region"

# Confirma que as credenciais autorizam uma consulta AWS na região.
aws ec2 describe-availability-zones --region $Region --profile default --query 'AvailabilityZones[0].ZoneName' --output text

# Confirme que o kubeconfig existente está presente e responda pelo cluster ACTA.
if (-not (Test-Path -LiteralPath $Kubeconfig)) { throw "Kubeconfig ACTA ausente: $Kubeconfig. Pare; não crie outro nem troque de cluster." }
kubectl --kubeconfig $Kubeconfig config current-context
kubectl --kubeconfig $Kubeconfig cluster-info
kubectl --kubeconfig $Kubeconfig get nodes -o wide
kubectl --kubeconfig $Kubeconfig auth can-i get deployments -n acta-prod
kubectl --kubeconfig $Kubeconfig auth can-i patch deployments -n acta-prod
```

Se `get-caller-identity` ou a consulta AWS falhar por token expirado/ausente, pare. Se `cluster-info`, `get nodes` ou `auth can-i` falhar, pare e reporte exatamente a falha de acesso. `patch deployments` deve retornar `yes` para executar um rollout via `kubectl rollout restart`; se não retornar `yes`, não tente contornar a permissão.

Confira o alvo antes de agir. Não atualize kubeconfig via EKS: este é o cluster ACTA existente e o kubeconfig configurado pelo ambiente. Região AWS e endpoint Kubernetes são verificações distintas.

## Inventário de serviços

Trate um Deployment por vez e nesta ordem, avançando somente após registrar o resultado observado do serviço atual:

1. `acta-auth-api`
2. `acta-pg-api`
3. `acta-fcm-api`
4. `acta-mongo-api`
5. `acta-import-api`
6. `acta-ai`
7. `acta-mcp`

Use `$Service` para o serviço atual e rode as verificações antes de reiniciar:

```powershell
$Service = 'acta-auth-api' # Substitua pelo próximo Deployment, um de cada vez.

kubectl --kubeconfig $Kubeconfig get deployment $Service -n acta-prod -o wide
kubectl --kubeconfig $Kubeconfig describe deployment $Service -n acta-prod
kubectl --kubeconfig $Kubeconfig get pods -n acta-prod -l "app.kubernetes.io/name=$Service" -o wide
kubectl --kubeconfig $Kubeconfig get events -n acta-prod --field-selector type=Warning --sort-by=.lastTimestamp
```

Registre a imagem atual, réplicas desejadas/atualizadas/prontas/disponíveis, nomes e estado dos pods, condições/eventos relevantes e quaisquer sinais de falha. Confirme que pods saudáveis existentes continuam servindo antes de qualquer reinício.

Para cada pod listado, inspecione a configuração e logs recentes. O `describe pod` mostra nomes/referências de Secrets, sem revelar seus valores:

```powershell
$Pod = '<nome-do-pod>'
kubectl --kubeconfig $Kubeconfig describe pod $Pod -n acta-prod
kubectl --kubeconfig $Kubeconfig logs $Pod -n acta-prod --all-containers=true --since=30m --prefix=true
```

Se o container reiniciou, consulte também os logs anteriores:

```powershell
kubectl --kubeconfig $Kubeconfig logs $Pod -n acta-prod --all-containers=true --previous --prefix=true
```

Não execute `kubectl get secret -o yaml/json`, `kubectl describe secret`, comandos `printenv` no pod, nem qualquer comando que revele valores de Secrets. Examine apenas referências e estado de sincronização:

```powershell
kubectl --kubeconfig $Kubeconfig get infisicalsecrets -n acta-prod
kubectl --kubeconfig $Kubeconfig describe infisicalsecret -n acta-prod
```

Confirme que os recursos InfisicalSecret associados estão prontos/sincronizados e que os pods referenciam os Secrets necessários. Se um Secret esperado estiver ausente ou não sincronizado, não reinicie: registre o bloqueio e pare esse serviço para investigação autorizada.

## Decidir e executar cada rollout

- **Não reinicie por rotina.** Se o Deployment já usa a imagem esperada e todos os pods estão prontos, sem alteração de Secret pendente, não reinicie; registre que nenhuma ação foi necessária.
- Só reinicie quando necessário e autorizado: por exemplo, quando a imagem desejada já estiver reconciliada no Deployment, ou quando uma rotação/sincronização de Secret comprovada requerer que o pod releia a configuração. Não edite a imagem nem faça sync do Argo CD nesta sessão.
- Antes de reiniciar, confira novamente readiness, imagem e Secrets, além da autorização de `patch` validada acima. Preserve os pods saudáveis durante a atualização.
- Faça somente um restart por vez. Não avance ao próximo Deployment até o rollout atual concluir ou falhar e seu resultado estar registrado.

```powershell
kubectl --kubeconfig $Kubeconfig rollout restart deployment/$Service -n acta-prod
kubectl --kubeconfig $Kubeconfig rollout status deployment/$Service -n acta-prod --timeout=10m
```

Se o rollout falhar ou expirar, não repita o restart em loop. Registre o erro, então colete estado, pods, eventos e logs como na seção anterior. Preserve réplicas antigas saudáveis; pare a sequência e reporte o bloqueio antes de avançar para outro serviço.

## Health checks

Descubra os hosts atuais a partir dos Ingresses; não reutilize IPs/hosts antigos:

```powershell
kubectl --kubeconfig $Kubeconfig get ingress -n acta-prod -o custom-columns='NAME:.metadata.name,HOST:.spec.rules[0].host'
```

Use o host atualmente retornado para cada serviço. Os caminhos de health conhecidos são:

| Deployment | Caminho |
| --- | --- |
| `acta-auth-api` | `/api/v1/health` |
| `acta-pg-api` | `/api/v1/health` |
| `acta-fcm-api` | `/health` |
| `acta-mongo-api` | `/api/v1/health` |
| `acta-import-api` | `/docs` (verifica disponibilidade HTTP da documentação; não é health agregado) |
| `acta-ai` | `/health` |
| `acta-mcp` | `/health` (verificação pública de disponibilidade; o endpoint MCP é `/mcp`) |

Faça consultas HTTPS somente de leitura e registre status HTTP ou erro sem despejar headers/tokens:

```powershell
$HealthUrl = 'https://<host-atual>/<caminho>'
try {
    $Response = Invoke-WebRequest -Uri $HealthUrl -Method Get -TimeoutSec 15
    "HTTP $([int]$Response.StatusCode) · $HealthUrl"
} catch {
    $Status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'falha de conexão' }
    "$Status · $HealthUrl"
}
```

Não assuma que HTTP 200 em uma dependência comprova saúde agregada; confira também as dependências e o endpoint do serviço específico.

## Relatório final

Ao terminar ou parar por bloqueio, informe por Deployment:

- imagem implantada;
- réplicas desejadas e prontas (inclua disponíveis/atualizadas se úteis);
- ação tomada ou motivo para não reiniciar;
- resultado observado do rollout: concluído, falhou, expirou ou não necessário;
- URL/caminho e resultado do health check, ou indisponível/não verificado;
- erros/eventos relevantes e bloqueios.

Não inclua credenciais, valores de Secrets, tokens, conteúdo sensível de logs nem transcrições com dados secretos. Não declare sucesso com base somente no estado EC2 ou `Running`: pods precisam estar prontos, o rollout precisa concluir e os health checks disponíveis precisam ser avaliados.
