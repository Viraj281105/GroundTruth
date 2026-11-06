{{- define "gt.image" -}}
{{- $r := .root.Values.image.registry -}}
{{- if $r }}{{ $r }}/{{ end }}{{ .name }}:{{ .tag }}
{{- end -}}
{{- define "gt.env" -}}
envFrom:
  - configMapRef:
      name: {{ .Release.Name }}-config
  - secretRef:
      name: {{ .Values.existingSecret }}
{{- end -}}
