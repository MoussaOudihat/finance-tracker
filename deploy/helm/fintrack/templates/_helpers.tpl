{{/* Nom court du chart */}}
{{- define "fintrack.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Libellés communs (recommandations Kubernetes), SANS instance : à
     combiner avec fintrack.selector (qui la porte) sur les objets d'un composant. */}}
{{- define "fintrack.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/part-of: fintrack
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Libellés complets d'un objet sans composant (ConfigMap, Secret…) */}}
{{- define "fintrack.labelsAll" -}}
{{ include "fintrack.labels" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Sélecteur d'un composant : (dict "ctx" $ "name" "web") */}}
{{- define "fintrack.selector" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
{{- end -}}

{{/* Image d'un service : digest si fourni, sinon tag (défaut : appVersion) */}}
{{- define "fintrack.image" -}}
{{- $img := .ctx.Values.image -}}
{{- $repo := printf "%s/%s%s" $img.registry $img.prefix .name -}}
{{- $digest := get ($img.digests | default dict) .name -}}
{{- if $digest -}}
{{ $repo }}@{{ $digest }}
{{- else -}}
{{ $repo }}:{{ $img.tag | default .ctx.Chart.AppVersion }}
{{- end -}}
{{- end -}}

{{/* Nom du Secret applicatif */}}
{{- define "fintrack.secretName" -}}
{{- .Values.secrets.existingSecret | default (printf "%s-secrets" .Release.Name) -}}
{{- end -}}

{{/* Contexte de sécurité commun des pods (Pod Security « restricted ») */}}
{{- define "fintrack.podSecurity" -}}
runAsNonRoot: true
runAsUser: {{ .uid | default 10001 }}
runAsGroup: {{ .gid | default 10001 }}
fsGroup: {{ .gid | default 10001 }}
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "fintrack.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end -}}

{{/* URL publique du serveur MCP (identifiant de ressource OAuth) */}}
{{- define "fintrack.mcpPublicUrl" -}}
{{- if .Values.mcp.publicUrl -}}
{{ .Values.mcp.publicUrl }}
{{- else -}}
https://{{ .Values.ingress.host }}/mcp
{{- end -}}
{{- end -}}

{{/* Chemin du serveur MCP, déduit de l'URL publique (Ingress = application) */}}
{{- define "fintrack.mcpPath" -}}
{{- $u := urlParse (include "fintrack.mcpPublicUrl" .) -}}
{{- if ne $u.host .Values.ingress.host -}}
{{- fail (printf "mcp.publicUrl doit utiliser l'hôte de l'Ingress (%s), reçu : %s" .Values.ingress.host $u.host) -}}
{{- end -}}
{{- if or (not $u.path) (eq $u.path "/") -}}
{{- fail "mcp.publicUrl doit contenir un chemin, ex. https://<hôte>/mcp" -}}
{{- end -}}
{{- $u.path -}}
{{- end -}}

{{/* URL de redirection TickTick par défaut */}}
{{- define "fintrack.ticktickRedirect" -}}
{{- if .Values.config.ticktickRedirectUri -}}
{{ .Values.config.ticktickRedirectUri }}
{{- else -}}
{{ ternary "https" "http" .Values.ingress.tls.enabled }}://{{ .Values.ingress.host }}/parametres/ticktick/callback
{{- end -}}
{{- end -}}
