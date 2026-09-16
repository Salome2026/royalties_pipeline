# Monitoreo operativo

`OPS-001` protege el circuito productivo sin cambiar calculos ni pantallas.

## Salud

- `/health` informa base operativa, modo de marts, release activo, fallback y
  ultimo error conocido.
- `/health/ready` fuerza la verificacion del manifiesto usando el resumen
  compacto de statements. Devuelve HTTP 503 si Cloud SQL, la descarga del
  release o la cache no estan saludables.
- El uptime check publico consulta `/health/ready` cada minuto y exige que
  `$.status` sea `ok`.

## Alertas

Las politicas administradas por `scripts/configure_ops_monitoring.py` son:

| Politica | Umbral |
| --- | --- |
| VPO API - disponibilidad | menos de 80% de ubicaciones saludables durante 2 minutos |
| VPO API - errores 5xx | al menos un 5xx en una ventana de 5 minutos |
| VPO API - latencia p95 | mas de 30 segundos durante 5 minutos |
| VPO API - memoria | mas de 85% durante 5 minutos |
| VPO reportes - ejecucion fallida | al menos una ejecucion fallida |

La instalacion es idempotente por nombre de politica. El correo no se guarda en
Git y se entrega como parametro:

```powershell
python scripts/configure_ops_monitoring.py --email usuario@dominio.com
python scripts/configure_ops_monitoring.py --email usuario@dominio.com --apply
```

## Despliegue

Despues de actualizar API y Job, Cloud Build comprueba:

- misma imagen del commit en ambos destinos;
- 100% del trafico en la revision nueva;
- `/health/ready` con estado `ok`;
- release activo;
- cache sin fallback ni ultimo error.

Si cualquiera de esos controles falla, el build queda fallido y el despliegue
no se considera alineado.

## Linea base

Medicion previa del 2026-09-16, ultimas 24 horas:

- 7 respuestas HTTP 5xx;
- latencia p95 horaria maxima: 231.9 segundos;
- memoria p95 horaria maxima: 42.8%;
- no habia politicas ni canales de notificacion configurados.

El release analitico activo al iniciar OPS-001 era
`20260916T065558Z-4270970b55a3`.
