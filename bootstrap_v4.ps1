# Signal Watch - bootstrap del repositorio (arbol v4) - version PowerShell
# Uso:  .\bootstrap_v4.ps1
# Idempotente: NO pisa archivos que ya existen (tus entregas estan a salvo).
# NO crea archivos generados (frozen/*.yaml, fixtures) - nacen del codigo.

$ErrorActionPreference = "Stop"

# Crea un archivo vacio solo si no existe, creando su carpeta si hace falta
function New-EmptyFile($path) {
    $dir = Split-Path -Parent $path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (-not (Test-Path $path)) { New-Item -ItemType File -Path $path -Force | Out-Null }
}

$files = @(
  # --- CI y config ---
  ".github/workflows/ci.yml", ".github/workflows/reproducibility.yml",
  ".github/PULL_REQUEST_TEMPLATE.md", ".streamlit/config.toml",
  # --- configs ---
  "configs/logging.yaml", "configs/economic_value.yaml",
  "configs/sources/french.yaml", "configs/sources/lending_club.yaml",
  "configs/sources/kaggle_term.yaml", "configs/sources/checksums.yaml",
  "configs/synthetic/calibracion.yaml", "configs/synthetic/evaluacion.yaml",
  "configs/synthetic/escenarios_extendidos.yaml", "configs/synthetic/evaluacion_ruido_real.yaml",
  "configs/detectors/baseline_3sigma.yaml", "configs/detectors/umbral_fijo_psi.yaml",
  "configs/detectors/cusum.yaml", "configs/detectors/page_hinkley.yaml", "configs/detectors/bocpd.yaml",
  "configs/detectors/frozen/CHANGELOG_configs.md",
  "configs/streams/credito_lc_auc_36m.yaml", "configs/streams/credito_lc_psi_36m.yaml",
  "configs/streams/factor_hml_sharpe.yaml", "configs/streams/factor_mom_sharpe.yaml",
  "configs/streams/factor_mkt_sharpe.yaml", "configs/streams/factor_smb_sharpe.yaml",
  "configs/streams/sint_scorecard_auc.yaml", "configs/streams/sint_scorecard_psi.yaml",
  "configs/streams/sint_factor_sharpe.yaml",
  # --- data (contenido ignorado por git) ---
  "data/README.md", "data/raw/french/.gitkeep", "data/raw/lending_club/.gitkeep",
  "data/raw/_metadata/.gitkeep", "data/processed/.gitkeep",
  "data/gold/real/.gitkeep", "data/gold/synthetic/.gitkeep",
  # --- src ---
  "src/signal_watch/__init__.py", "src/signal_watch/py.typed", "src/signal_watch/exceptions.py",
  "src/signal_watch/paths.py", "src/signal_watch/config.py", "src/signal_watch/logging_conf.py",
  "src/signal_watch/cli.py",
  "src/signal_watch/ingest/__init__.py", "src/signal_watch/ingest/french.py",
  "src/signal_watch/ingest/lending_club.py", "src/signal_watch/ingest/kaggle_term_join.py",
  "src/signal_watch/ingest/checksums.py",
  "src/signal_watch/processing/__init__.py", "src/signal_watch/processing/factor_returns.py",
  "src/signal_watch/processing/loans_clean.py", "src/signal_watch/processing/privacy.py",
  "src/signal_watch/processing/maturity_rules.py", "src/signal_watch/processing/validators.py",
  "src/signal_watch/gold/__init__.py", "src/signal_watch/gold/schemas.py",
  "src/signal_watch/gold/metric_stream.py", "src/signal_watch/gold/factor_metrics.py",
  "src/signal_watch/gold/loans_scorecard.py", "src/signal_watch/gold/vintage_metrics.py",
  "src/signal_watch/scorecard/__init__.py", "src/signal_watch/scorecard/features.py",
  "src/signal_watch/scorecard/preprocessing.py", "src/signal_watch/scorecard/train.py",
  "src/signal_watch/scorecard/evaluate.py", "src/signal_watch/scorecard/psi.py",
  "src/signal_watch/scorecard/vintage_backtest.py", "src/signal_watch/scorecard/woe.py",
  "src/signal_watch/synthetic/__init__.py", "src/signal_watch/synthetic/generator.py",
  "src/signal_watch/synthetic/scenarios.py", "src/signal_watch/synthetic/metrics.py",
  "src/signal_watch/synthetic/build_gold.py",
  "src/signal_watch/detectors/__init__.py", "src/signal_watch/detectors/base.py",
  "src/signal_watch/detectors/baseline.py", "src/signal_watch/detectors/cusum.py",
  "src/signal_watch/detectors/page_hinkley.py", "src/signal_watch/detectors/bocpd.py",
  "src/signal_watch/detectors/calibration.py", "src/signal_watch/detectors/registry.py",
  "src/signal_watch/evaluation/__init__.py", "src/signal_watch/evaluation/arl.py",
  "src/signal_watch/evaluation/delay_curves.py", "src/signal_watch/evaluation/error_analysis.py",
  "src/signal_watch/evaluation/deflated_sharpe.py", "src/signal_watch/evaluation/economic_value.py",
  "src/signal_watch/monitoring/__init__.py", "src/signal_watch/monitoring/engine.py",
  "src/signal_watch/monitoring/alarms.py", "src/signal_watch/monitoring/verdict.py",
  "src/signal_watch/monitoring/explain.py", "src/signal_watch/monitoring/audit_log.py",
  "src/signal_watch/reporting/__init__.py", "src/signal_watch/reporting/figures.py",
  "src/signal_watch/reporting/mrm_report.py",
  "src/signal_watch/reporting/templates/informe_mrm.md.j2",
  "src/signal_watch/reporting/templates/registro_auditoria.csv.j2",
  "src/signal_watch/reporting/templates/styles.css",
  # --- app ---
  "app/Home.py", "app/pages/1_Salud_de_modelos.py", "app/pages/2_Credito_LendingClub.py",
  "app/pages/3_Factores_de_mercado.py", "app/pages/4_Banco_de_pruebas.py",
  "app/pages/5_Valor_economico.py", "app/pages/6_Informe_MRM.py",
  "app/components/__init__.py", "app/components/metric_chart.py", "app/components/alarm_markers.py",
  "app/components/verdict_card.py", "app/components/delay_curve_plot.py",
  "app/components/audit_table.py", "app/components/sidebar_filters.py",
  "app/state/__init__.py", "app/state/session.py", "app/assets/styles.css",
  # --- notebooks ---
  "notebooks/_template.ipynb", "notebooks/01_eda_censura_y_cosechas.ipynb",
  "notebooks/02_eda_factores_episodios.ipynb", "notebooks/03_scorecard_entrenamiento.ipynb",
  "notebooks/04_calibracion_detectores.ipynb", "notebooks/05_curvas_retardo_falsas_alarmas.ipynb",
  "notebooks/06_arl0_del_folclore_psi.ipynb", "notebooks/07_deflated_sharpe.ipynb",
  "notebooks/08_validacion_real_credito.ipynb", "notebooks/09_validacion_real_mercado.ipynb",
  "notebooks/10_ruido_real_recalibracion.ipynb", "notebooks/11_valor_economico.ipynb",
  # --- scripts ---
  "scripts/download_data.py", "scripts/build_processed.py", "scripts/build_gold.py",
  "scripts/build_synthetic.py", "scripts/train_scorecard.py", "scripts/calibrate_detectors.py",
  "scripts/freeze_config.py", "scripts/run_evaluation.py", "scripts/run_monitoring.py",
  "scripts/generate_mrm_report.py", "scripts/reproduce_all.sh",
  # --- tests ---
  "tests/conftest.py",
  "tests/unit/test_gold_schemas.py", "tests/unit/test_generator.py", "tests/unit/test_scenarios.py",
  "tests/unit/test_synthetic_metrics.py", "tests/unit/test_baseline.py", "tests/unit/test_cusum.py",
  "tests/unit/test_page_hinkley.py", "tests/unit/test_calibration.py", "tests/unit/test_bocpd.py",
  "tests/unit/test_arl.py", "tests/unit/test_deflated_sharpe.py", "tests/unit/test_economic_value.py",
  "tests/unit/test_maturity_rules.py", "tests/unit/test_privacy_columns.py", "tests/unit/test_psi.py",
  "tests/unit/test_verdict.py", "tests/unit/test_audit_log.py",
  "tests/integration/test_metric_stream_contract.py", "tests/integration/test_pipeline_raw_to_gold.py",
  "tests/integration/test_monitoring_engine.py", "tests/integration/test_mrm_report_export.py",
  "tests/methodology/test_tau_no_cruza_la_muralla.py",
  "tests/methodology/test_calibracion_evaluacion_disjuntas.py",
  "tests/methodology/test_configs_congeladas_antes_de_evaluar.py",
  "tests/methodology/test_cosechas_censuradas_excluidas.py",
  "tests/methodology/test_split_temporal_sin_leakage.py",
  "tests/methodology/test_sin_features_post_concesion.py",
  "tests/fixtures/.gitkeep", "tests/smoke/test_cli.py", "tests/smoke/test_app_carga.py",
  # --- docs (NO toca entregas existentes) ---
  "docs/glosario.md", "docs/limitaciones_y_trabajo_futuro.md", "docs/diccionario_datos.md",
  "docs/reproducibilidad.md", "docs/guia_usuario.md", "docs/model_card_monitor.md",
  "docs/model_card_scorecard.md", "docs/data_card_lending_club.md", "docs/data_card_french.md",
  "docs/privacidad.md",
  "docs/arquitectura/vision_general.md", "docs/arquitectura/capas_datos.md",
  "docs/arquitectura/contrato_metric_stream.md", "docs/arquitectura/diagrama_flujo.mermaid",
  "docs/arquitectura/decisiones/0001-alcance-credito-limitado-a-36-meses.md",
  "docs/arquitectura/decisiones/0002-contrato-antes-que-los-datos.md",
  "docs/arquitectura/decisiones/0003-sintetico-como-instrumento-de-medida.md",
  "docs/arquitectura/decisiones/0004-calibracion-y-evaluacion-disjuntas.md",
  "docs/arquitectura/decisiones/0005-persistencia-parquet-y-cadena-de-hashes.md",
  "docs/arquitectura/decisiones/0006-french-tres-factores-mas-momentum.md",
  "docs/arquitectura/decisiones/0007-ventana-movil-solapada-y-autocorrelacion.md",
  "docs/arquitectura/decisiones/0008-distribucion-nula-del-psi.md",
  "docs/arquitectura/decisiones/0009-zenodo-modela-kaggle-solo-aporta-term.md",
  "docs/arquitectura/decisiones/0010-exclusion-de-grade-e-int-rate.md",
  "docs/arquitectura/decisiones/0011-tamano-minimo-de-cosecha.md",
  "docs/arquitectura/decisiones/0012-woe-como-sensibilidad-no-como-base.md",
  "docs/entregas/04_analisis_modelado.md", "docs/entregas/05_diseno_frontal.md",
  "docs/entregas/06_mvp_y_conclusiones.md",
  "docs/mrm/mapeo_sr11-7.md", "docs/mrm/mapeo_eu_ai_act.md",
  "docs/mrm/plantilla_informe_validacion.md", "docs/mrm/ejemplo_registro_auditoria.csv",
  "docs/memoria/memoria_final.md", "docs/memoria/bibliografia.bib", "docs/memoria/figuras/.gitkeep",
  "docs/defensa/presentacion.md", "docs/defensa/guion_defensa.md",
  # --- outputs ---
  "outputs/figures/.gitkeep", "outputs/tables/.gitkeep", "outputs/reports/.gitkeep",
  "outputs/audit/.gitkeep",
  # --- raiz ---
  "Makefile", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
  ".pre-commit-config.yaml", "CHANGELOG.md", "CITATION.cff", "LICENSE", "README.md"
)

Write-Host "-> Creando estructura del arbol v4..." -ForegroundColor Cyan
$creados = 0
foreach ($f in $files) {
    if (-not (Test-Path $f)) { $creados++ }
    New-EmptyFile $f
}

# .gitignore (solo si no existe)
if (-not (Test-Path ".gitignore")) {
@"
# datos: nunca se versionan, se regeneran
data/raw/**
data/processed/**
data/gold/**
!data/**/.gitkeep
!data/README.md
# salidas
outputs/figures/**
outputs/reports/**
outputs/audit/**
!outputs/**/.gitkeep
# outputs/tables/ SI se versiona: es la evidencia
# python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
# notebooks
.ipynb_checkpoints/
# entorno
.env
.DS_Store
"@ | Out-File -FilePath ".gitignore" -Encoding utf8
    Write-Host "  . .gitignore escrito" -ForegroundColor Green
}

# .gitattributes (solo si no existe)
if (-not (Test-Path ".gitattributes")) {
@"
* text=auto eol=lf
*.parquet binary
*.png      binary
*.pdf      binary
*.ipynb    -diff
"@ | Out-File -FilePath ".gitattributes" -Encoding utf8
    Write-Host "  . .gitattributes escrito" -ForegroundColor Green
}

Write-Host ""
Write-Host "OK - Arbol v4 creado." -ForegroundColor Green
$carpetas = (Get-ChildItem -Recurse -Directory | Where-Object { $_.FullName -notmatch '\\\.git\\' }).Count
$archivos = (Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '\\\.git\\' }).Count
Write-Host "  carpetas: $carpetas"
Write-Host "  archivos: $archivos"
Write-Host "  archivos nuevos creados en esta pasada: $creados"
