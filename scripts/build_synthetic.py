"""Script: genera el banco de pruebas completo y lo guarda en disco.

Produce DOS conjuntos completamente separados, con semillas que NUNCA
se solapan:
  · data/gold/synthetic/calibracion.parquet  — para ajustar detectores
  · data/gold/synthetic/evaluacion.parquet   — para medir su rendimiento

Por qué la separación es obligatoria (no opcional):
  Si calibras y evalúas sobre las MISMAS series, el resultado está
  inflado — es como estudiar para un examen con las preguntas ya
  filtradas. El detector "ha visto" esos datos al ajustarse, así que
  medir su rendimiento ahí no dice nada sobre cómo se comportará con
  datos nuevos. Las semillas disjuntas son la garantía mecánica de que
  esto no puede pasar por accidente (test_calibracion_evaluacion_disjuntas).

Uso:
    python scripts/build_synthetic.py
    (o, una vez tengamos el subcomando en cli.py: signal-watch build-synthetic)
"""

from __future__ import annotations

from signal_watch.gold.metric_stream import save_ground_truth, save_metric_stream
from signal_watch.paths import PATHS
from signal_watch.synthetic.build_gold import EscenarioConfig, generar_stream

# ── Parámetros del banco de pruebas ───────────────────────────────────

N_PERIODOS = 100  # longitud de cada serie sintética
N_REPLICAS = 200  # cuántas series por combinación (escenario x tau x delta)
N_OBS_BASE = 800  # tamaño de muestra típico de cada periodo

# Escenarios y magnitudes a cubrir. Cada combinación se repite
# N_REPLICAS veces (con semillas distintas) para tener suficientes
# series como para medir el retardo y las falsas alarmas con confianza
# estadística, no con una sola serie suelta.
ESCENARIOS = ("salto", "deriva", "cambio_varianza", "sin_cambio")
DELTAS_SIGMA = (0.5, 1.0, 1.5, 2.0, 3.0)  # magnitudes de cambio a probar
TAU_FRACCION = 0.4  # el cambio ocurre al 40% de la serie (deja "antes" y "después" de sobra)

# Rangos de semillas GARANTIZADAMENTE disjuntos: calibración usa
# 0..999999, evaluación usa 1000000 en adelante. No hay solapamiento
# posible por construcción, no por buena suerte.
SEMILLA_BASE_CALIBRACION = 0
SEMILLA_BASE_EVALUACION = 1_000_000


def _construir_configs(
    tipo_metrica: str,
    semilla_base: int,
    prefijo: str,
) -> list[EscenarioConfig]:
    """Construye la lista completa de configuraciones a generar para
    un conjunto (calibración o evaluación).

    Recorre todos los escenarios y, para los que tienen cambio (todos
    menos sin_cambio), todas las magnitudes delta. sin_cambio no varía
    con delta (no hay cambio que escalar), así que solo se genera una
    vez por réplica.
    """
    configs = []
    seed = semilla_base
    tau = int(N_PERIODOS * TAU_FRACCION)

    for escenario in ESCENARIOS:
        deltas = (0.0,) if escenario == "sin_cambio" else DELTAS_SIGMA
        tau_efectivo = None if escenario == "sin_cambio" else tau

        for delta in deltas:
            for replica in range(N_REPLICAS):
                nombre = (
                    f"{prefijo}_{tipo_metrica}_{escenario}_"
                    f"d{delta:.1f}_r{replica:03d}"
                )
                configs.append(
                    EscenarioConfig(
                        nombre=nombre,
                        tipo_metrica=tipo_metrica,
                        escenario=escenario,
                        n=N_PERIODOS,
                        tau=tau_efectivo,
                        delta_sigma=delta,
                        rho=0.5,
                        n_obs_base=N_OBS_BASE,
                        seed=seed,
                    )
                )
                seed += 1
    return configs


def construir_banco(semilla_base: int, prefijo: str) -> tuple[list, list]:
    """Genera TODAS las series (AUC y PSI, todos los escenarios) para
    un conjunto (calibración o evaluación), y devuelve las observaciones
    y ground truths de todas ellas, aplanadas en dos listas paralelas.
    """
    configs_auc = _construir_configs("auc", semilla_base, prefijo)
    configs_psi = _construir_configs(
        "psi", semilla_base + 500_000, prefijo
    )  # +500k: separa el espacio de semillas de auc y psi también

    todas_obs = []
    todos_gt = []
    for cfg in configs_auc + configs_psi:
        obs, gt = generar_stream(cfg)
        todas_obs.append(obs)
        todos_gt.append(gt)
    return todas_obs, todos_gt


def main() -> None:
    print("Construyendo banco de pruebas sintético...")
    print(f"  {len(ESCENARIOS)} escenarios x {len(DELTAS_SIGMA)} magnitudes x "
          f"{N_REPLICAS} réplicas x 2 métricas (aprox.)")

    # ── Calibración ──
    print("\n[1/2] Generando conjunto de CALIBRACIÓN...")
    obs_calib, gt_calib = construir_banco(SEMILLA_BASE_CALIBRACION, "sint_calib")
    print(f"  {len(obs_calib)} streams generados")

    ruta_calib_obs = PATHS.data_gold_synthetic / "calibracion.parquet"
    ruta_calib_gt = PATHS.data_gold_synthetic / "calibracion_ground_truth.parquet"

    # aplanar: todas las observaciones de todos los streams en una tabla
    todas_obs_calib = [o for stream in obs_calib for o in stream]
    save_metric_stream(todas_obs_calib, ruta_calib_obs)
    save_ground_truth(gt_calib, ruta_calib_gt)
    print(f"  Guardado: {ruta_calib_obs}")
    print(f"  Guardado: {ruta_calib_gt}")

    # ── Evaluación ──
    print("\n[2/2] Generando conjunto de EVALUACIÓN...")
    obs_eval, gt_eval = construir_banco(SEMILLA_BASE_EVALUACION, "sint_eval")
    print(f"  {len(obs_eval)} streams generados")

    ruta_eval_obs = PATHS.data_gold_synthetic / "evaluacion.parquet"
    ruta_eval_gt = PATHS.data_gold_synthetic / "evaluacion_ground_truth.parquet"

    todas_obs_eval = [o for stream in obs_eval for o in stream]
    save_metric_stream(todas_obs_eval, ruta_eval_obs)
    save_ground_truth(gt_eval, ruta_eval_gt)
    print(f"  Guardado: {ruta_eval_obs}")
    print(f"  Guardado: {ruta_eval_gt}")

    # ── Verificación de la regla de semillas disjuntas (R4) ──
    #
    # Hay CUATRO rangos de semillas en juego, no dos: cada conjunto
    # (calibración / evaluación) se divide a su vez en AUC y PSI, con un
    # desplazamiento de +500.000 entre métricas. Comprobar solo el par
    # AUC-calibración / AUC-evaluación verificaría un cuarto de R4 y
    # dejaría sin vigilar, por ejemplo, que AUC-calibración no alcance a
    # PSI-calibración si algún día sube N_REPLICAS.
    #
    # Se comprueban los seis pares posibles. Con N_REPLICAS=200 el margen
    # es enorme (harían falta más de 31.000 réplicas para que el primer
    # par colisionara), pero la aserción debe verificar lo que dice
    # verificar, no una parte cómoda.
    rangos = {
        "auc_calib": {c.seed for c in _construir_configs("auc", SEMILLA_BASE_CALIBRACION, "x")},
        "psi_calib": {c.seed for c in _construir_configs("psi", SEMILLA_BASE_CALIBRACION + 500_000, "x")},
        "auc_eval": {c.seed for c in _construir_configs("auc", SEMILLA_BASE_EVALUACION, "x")},
        "psi_eval": {c.seed for c in _construir_configs("psi", SEMILLA_BASE_EVALUACION + 500_000, "x")},
    }
    for a, b in [(x, y) for x in rangos for y in rangos if x < y]:
        comun = rangos[a] & rangos[b]
        assert not comun, (
            f"¡VIOLACIÓN DE R4! {a} y {b} comparten semillas "
            f"(ejemplo: {sorted(comun)[:5]})"
        )
    print("\nVerificado (R4): los 4 rangos de semillas son disjuntos dos a dos.")
    for nombre, s in sorted(rangos.items()):
        print(f"    {nombre:10} {min(s):>9,} .. {max(s):>9,}  ({len(s)} semillas)")
    print(f"\nBanco de pruebas completo: {len(todas_obs_calib) + len(todas_obs_eval)} "
          f"observaciones totales.")


if __name__ == "__main__":
    main()