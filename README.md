```
docker build -t resume-analyzer .
docker run --env-file .env -p 8501:8501 resume-analyzer
```