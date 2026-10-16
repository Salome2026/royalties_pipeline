# Publicacion controlada de ONErpm

Autorizacion de Ruben: 2026-10-16. Publicar la mejora validada en cloud sin
cambiar importes, asociados, contratos cerrados, reportes actuales o Shares
In & Out. Codigo base observado: 3f79197.

## Alcance

Se promueven el lector de metadata ONErpm, el enriquecimiento del catalogo y
las propuestas de participantes en Contratos. No se importa la base, usuarios,
contratos, historial ni fixtures del entorno de prueba.

La version probada en cloud se conserva en `onerpm_cloud_refresh_20261015.md`.
Esta entrega agrega dos defensas de entrada: cuentas configuradas y XLSX
certificados. Los formatos no certificados fallan antes de procesar importes.
Las funciones economicas y las policies de Shares no se modifican.

## Secuencia y controles obligatorios

1. Snapshot de contratos/historiales y policies, manifiesto GCS con generaciones,
   codigo de API/Job y estado de BigQuery vigente.
2. Relectura de todos los XLSX y comparacion del candidato: solo cuatro columnas
   artisticas, aliases y entrada de reportes identicos, idempotencia y AST
   economico conservado. Pruebas Python, TypeScript y build web antes de push.
3. Commit acotado sobre main actual; CI rector publica API y Job con la misma
   imagen. El frontend de Vercel sigue su despliegue normal desde ese commit.
4. Backup recuperable de `royalty_catalog`, staging y transaccion que actualiza
   solo `catalog_artists`, `catalog_artist_statement`, `catalog_artist_rule` y
   `catalog_artist_evidence` para las claves existentes del release vigente.
5. Catalogo y companion inmutables en GCS. Cambio de puntero por generacion
   esperada, conservando release economico y los otros cinco objetos. Se
   actualiza solo la generacion de manifiesto del registro analitico.
6. Control final por HTTP de importes, meses y asociados; hashes de todos los
   contratos/historiales y policies, campos no artisticos en BigQuery y Parquet,
   salud sin fallback obsoleto, trafico y alineacion API/Job/frontend.

No se guarda ni modifica un contrato real como prueba. El recorrido de guardar,
quitar, agregar, reabrir y rechazar cambios de un cerrado fue validado en la
copia cloud. En produccion se verifica solo por lecturas y estado de despliegue.

## Evidencia y recuperacion

Directorio de trabajo:
`C:/royalties_pipeline/staging/catalogo_lectura/20261016_onerpm_production/`.

`baseline.json` congela los originales; `catalog_verification.json` registra el
candidato; `publication.json` conserva el avance de la publicacion, objeto
anterior y backup BigQuery. `certification.json` se genera solamente despues
del control final y es el recibo de estado real, no una prediccion de este doc.
Los respaldos de metadata y el recibo se conservan en `marts/catalog_revisions/`.
Los snapshots de SQL con credenciales o datos operativos quedan privados
localmente; no se suben como evidencia publica ni al repositorio.

Si falla la validacion de metadata, se detiene el avance. La recuperacion usa
la generacion anterior del catalogo y solo las cuatro columnas del backup de
BigQuery; nunca restaura una base operativa ni reimputa dinero. Un rollback de
codigo usa la revision previa de API y el digest previo del Job. Toda vuelta
de puntero usa comparacion de generacion para no pisar publicaciones ajenas.

La copia local canonica de los dos Parquet de metadata se actualiza despues
de verificar la publicacion, conservando un respaldo de su version previa.
No se reescriben codigo sucio ni otros worktrees.
