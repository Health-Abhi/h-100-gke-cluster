{{- define "baseline.teamName" -}}
{{- printf "team-%s" (.Values.access.team | lower | replace "_" "-" | trunc 45 | trimSuffix "-") -}}
{{- end -}}
