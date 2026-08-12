web: gunicorn -c gunicorn.conf.py app:app
worker: python -m backend.worker.runner
autonomy: python -m backend.nexus_research_ai_autonomy.research_autonomy_service --run --campaign-root /data/campaigns/research_v18_2_30 --cycle-sleep-sec 120
