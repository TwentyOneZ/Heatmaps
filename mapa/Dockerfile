FROM python:3.11-slim

WORKDIR /app
RUN mkdir -p /app/public

# copie tudo que o HTML usa (o próprio HTML + eventuais .json/.png/.js/.css)
COPY ./* /app/public/

# sirva na porta 5000
EXPOSE 80
CMD ["python", "-m", "http.server", "80", "--directory", "/app/public"]
