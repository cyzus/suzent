# SearXNG Setup Guide

This guide provides detailed instructions for setting up SearXNG, a privacy-respecting, self-hosted metasearch engine for use with Suzent's WebSearchTool.

## Table of Contents

- [Why SearXNG?](#why-searxng)
- [Prerequisites](#prerequisites)
- [Quick Setup](#quick-setup)
- [Detailed Configuration](#detailed-configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)
- [Maintenance](#maintenance)

---

## Why SearXNG?

SearXNG offers several advantages over traditional search APIs:

- **Privacy**: No user tracking, no profiling, no data collection
- **Aggregation**: Combines results from 70+ search engines
- **Customizable**: Configure which engines to use and how to weight results
- **Self-hosted**: Full control over your search infrastructure
- **Free**: No API keys or usage limits
- **Fast**: Results cached locally with Redis

**Performance Comparison:**
- Traditional API: 1-3 seconds + rate limits
- SearXNG: 500ms-1s + unlimited requests

---

## Prerequisites

- **Docker** and **Docker Compose** installed
- **WSL2** (for Windows users)
- **2GB RAM** minimum for the containers
- **Port 2077** available (or choose another port)

### Installing Docker

**Windows:**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Enable WSL2 backend in Docker Desktop settings

**Linux:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker.io docker-compose

# Enable and start Docker
sudo systemctl enable docker
sudo systemctl start docker
```

**macOS:**
1. Install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)

---

## Quick Setup

### Step 1: Create Directory Structure

```bash
# In your project root (or WSL for Windows users)
cd /path/to/suzent
mkdir -p searxng
```

### Step 2: Create docker-compose.yml

Create `docker-compose.yml` in your project root:

```yaml
services:
  caddy:
    container_name: caddy
    image: docker.io/library/caddy:2-alpine
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data:rw
      - caddy-config:/config:rw
    environment:
      - SEARXNG_HOSTNAME=${SEARXNG_HOSTNAME:-http://localhost}
      - SEARXNG_TLS=${LETSENCRYPT_EMAIL:-internal}
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"

  redis:
    container_name: redis
    image: docker.io/valkey/valkey:8-alpine
    command: valkey-server --save 30 1 --loglevel warning
    restart: unless-stopped
    networks:
      - searxng
    volumes:
      - valkey-data2:/data
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"

  searxng:
    container_name: searxng
    image: docker.io/searxng/searxng:latest
    restart: unless-stopped
    networks:
      - searxng
    ports:
      - "127.0.0.1:2077:8080"
    volumes:
      - ./searxng:/etc/searxng:rw
      - searxng-data:/var/cache/searxng:rw
    environment:
      - SEARXNG_BASE_URL=https://${SEARXNG_HOSTNAME:-localhost}/
    logging:
      driver: "json-file"
      options:
        max-size: "1m"
        max-file: "1"

networks:
  searxng:

volumes:
  caddy-data:
  caddy-config:
  valkey-data2:
  searxng-data:
```

### Step 3: Create SearXNG Configuration

Create `searxng/settings.yml`:

```yaml
# see https://docs.searxng.org/admin/settings/settings.html
use_default_settings: true

server:
  secret_key: "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY"  # IMPORTANT: Change this!
  limiter: false  # Disable for local API access
  image_proxy: true

search:
  # Enable JSON format for API access
  formats:
    - html
    - json
    - csv
    - rss

redis:
  url: redis://redis:6379/0

# Optional: Configure search engines
engines:
  - name: google
    disabled: false
  - name: bing
    disabled: false
  - name: duckduckgo
    disabled: false
  - name: brave
    disabled: false
  - name: wikipedia
    disabled: false
```

**Generate a secure secret key:**

```bash
# Linux/Mac/WSL
openssl rand -hex 32

# Or with Python
python -c "import secrets; print(secrets.token_hex(32))"

# Windows PowerShell
-join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | ForEach-Object {[char]$_})
```

Replace `CHANGE_THIS_TO_A_RANDOM_SECRET_KEY` with the generated key.

### Step 4: Configure Suzent

Add to your `.env` file:

```bash
# SearXNG Configuration
SEARXNG_BASE_URL=http://localhost:2077
```

### Step 5: Start SearXNG

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# Should show:
# NAME      IMAGE                          STATUS
# caddy     caddy:2-alpine                 Up
# redis     valkey/valkey:8-alpine         Up
# searxng   searxng/searxng:latest         Up
```

### Step 6: Verify Installation

**Test web interface:**
```bash
# Linux/Mac/WSL
curl http://localhost:2077/

# Windows PowerShell
Invoke-WebRequest -Uri "http://localhost:2077/"
```

**Test JSON API:**
```bash
# Linux/Mac/WSL
curl "http://localhost:2077/search?q=test&format=json"

# Windows PowerShell
Invoke-WebRequest -Uri "http://localhost:2077/search?q=test&format=json"
```

You should see JSON output with search results.

### Step 7: Start Suzent

```bash
python src/suzent/server.py
```

You should see in the logs:
```
WebSearch: Using SearXNG at http://localhost:2077
```

---

## Detailed Configuration

### Engine Configuration

SearXNG supports 70+ search engines. Configure in `searxng/settings.yml`:

```yaml
engines:
  # Web Search Engines
  - name: google
    disabled: false
    weight: 2  # Higher weight = more influence on results
    
  - name: bing
    disabled: false
    weight: 1
    
  - name: duckduckgo
    disabled: false
    weight: 1
    
  - name: brave
    disabled: false
    weight: 1
  
  # Specialized Engines
  - name: github
    disabled: false
    
  - name: stackoverflow
    disabled: false
    
  - name: wikipedia
    disabled: false
    
  # Disable unwanted engines
  - name: yahoo
    disabled: true
```

**Popular engines to consider:**
- `google` - Most comprehensive results
- `bing` - Good for news and images
- `duckduckgo` - Privacy-focused
- `brave` - Privacy-focused with own index
- `startpage` - Google results via proxy
- `qwant` - European privacy-focused
- `github` - For code searches
- `stackoverflow` - For programming questions
- `wikipedia` - For encyclopedic information

### Rate Limiting

For local development, disable rate limiting. For production, enable it:

```yaml
server:
  limiter: true

limiter:
  # Allow localhost without limits
  botdetection:
    ip_limit:
      link_token: true
    
    ip_lists:
      pass_ip:
        - 127.0.0.0/8    # IPv4 localhost
        - ::1/128        # IPv6 localhost
```

### Result Formatting

Configure result display:

```yaml
search:
  safe_search: 0  # 0=off, 1=moderate, 2=strict
  autocomplete: "google"
  default_lang: "en"
  max_page: 10
  
  # Output formats
  formats:
    - html
    - json
    - csv
    - rss
```

### Redis Configuration

Redis caches search results for better performance:

```yaml
redis:
  url: redis://redis:6379/0
  
# Optional: Configure cache times
outgoing:
  request_timeout: 3.0
  max_request_timeout: 10.0
```

---

## Testing

### Test Web Interface

Open in your browser:
```
http://localhost:2077
```

You should see the SearXNG search interface.

### Test JSON API

```bash
# Basic search
curl "http://localhost:2077/search?q=python&format=json"

# With parameters
curl "http://localhost:2077/search?q=AI&format=json&language=en&time_range=week"

# Windows PowerShell
Invoke-WebRequest -Uri "http://localhost:2077/search?q=python&format=json"
```

### Test from Suzent

Create a test script `test_search.py`:

```python
import os
import sys
sys.path.insert(0, 'src')

from suzent.tools.websearch_tool import WebSearchTool

tool = WebSearchTool()
results = tool.forward("artificial intelligence")
print(results)
```

Run:
```bash
python test_search.py
```

---

## Troubleshooting

### 403 Forbidden Error

**Symptoms:**
```
Error: SearXNG returned status 403
```

**Solutions:**

1. **Check settings.yml has JSON format enabled:**
   ```yaml
   search:
     formats:
       - html
       - json
   ```

2. **Disable limiter:**
   ```yaml
   server:
     limiter: false
   ```

3. **Restart container:**
   ```bash
   docker-compose restart searxng
   ```

4. **Check file permissions:**
   ```bash
   chmod -R 755 searxng/
   ```

### Container Won't Start

**Check logs:**
```bash
docker-compose logs searxng
```

**Common issues:**

1. **Port already in use:**
   ```bash
   # Check what's using port 2077
   sudo lsof -i :2077  # Linux/Mac
   netstat -ano | findstr :2077  # Windows
   
   # Change port in docker-compose.yml:
   ports:
     - "127.0.0.1:8080:8080"  # Use 8080 instead
   ```

2. **Invalid YAML syntax:**
   - Check indentation (use spaces, not tabs)
   - Validate YAML: https://www.yamllint.com/

3. **Missing secret_key:**
   - Must be set in settings.yml
   - Generate with: `openssl rand -hex 32`

### Connection Refused

**Check if containers are running:**
```bash
docker-compose ps
```

**Restart all services:**
```bash
docker-compose restart
```

**Check Docker network:**
```bash
docker network ls
docker network inspect suzent_searxng
```

### Slow Search Results

**Solutions:**

1. **Reduce engine count:**
   - Disable slow engines in settings.yml
   
2. **Increase timeout:**
   ```yaml
   outgoing:
     request_timeout: 5.0
     max_request_timeout: 15.0
   ```

3. **Check Redis:**
   ```bash
   docker-compose logs redis
   ```

### No Results Returned

**Check enabled engines:**
```yaml
engines:
  - name: google
    disabled: false  # Make sure this is false
```

**Test specific engine:**
```bash
curl "http://localhost:2077/search?q=test&format=json&engines=google"
```

**Check logs for engine errors:**
```bash
docker-compose logs -f searxng | grep ERROR
```

---

## Advanced Configuration

### Using a Different Port

**In docker-compose.yml:**
```yaml
ports:
  - "127.0.0.1:8080:8080"  # Change first port number
```

**In .env:**
```bash
SEARXNG_BASE_URL=http://localhost:8080
```

**Restart:**
```bash
docker-compose down
docker-compose up -d
```

### Public Instance (with HTTPS)

For public-facing instances:

1. **Get a domain** and point it to your server

2. **Update docker-compose.yml:**
   ```yaml
   environment:
     - SEARXNG_HOSTNAME=search.yourdomain.com
     - LETSENCRYPT_EMAIL=your@email.com
   ```

3. **Create Caddyfile:**
   ```
   {$SEARXNG_HOSTNAME} {
     reverse_proxy searxng:8080
   }
   ```

4. **Enable limiter in settings.yml:**
   ```yaml
   server:
     limiter: true
   ```

### Custom Engine

Add custom search engines:

```yaml
engines:
  - name: my_custom_engine
    engine: xpath
    search_url: https://example.com/search?q={query}
    results_xpath: //div[@class='result']
    url_xpath: .//a/@href
    title_xpath: .//h3/text()
    content_xpath: .//p[@class='snippet']/text()
```

### Docker Resource Limits

Limit resource usage:

```yaml
services:
  searxng:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          memory: 256M
```

---

## Maintenance

### View Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs searxng

# Follow logs
docker-compose logs -f searxng

# Last 100 lines
docker-compose logs --tail=100 searxng
```

### Update SearXNG

```bash
# Pull latest images
docker-compose pull

# Restart with new images
docker-compose up -d
```

### Backup Configuration

```bash
# Backup settings
tar -czf searxng-backup.tar.gz searxng/

# Restore
tar -xzf searxng-backup.tar.gz
```

### Clean Up

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (deletes cached data)
docker-compose down -v

# Remove images
docker rmi searxng/searxng:latest
```

### Monitor Performance

```bash
# Container stats
docker stats

# Specific container
docker stats searxng
```

---

## Related Documentation

- [Tools Guide](tools.md) - Using WebSearchTool with SearXNG
- [Configuration Guide](configuration.md) - Environment variables
- [Development Guide](development.md) - Custom tool development

## External Resources

- [SearXNG Official Documentation](https://docs.searxng.org/)
- [SearXNG GitHub Repository](https://github.com/searxng/searxng)
- [SearXNG Public Instances](https://searx.space/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)

---

## FAQ

**Q: Can I use an existing SearXNG instance?**
A: Yes! Just set `SEARXNG_BASE_URL` to any SearXNG instance URL in your `.env` file.

**Q: Do I need SearXNG to use Suzent?**
A: No, WebSearchTool automatically falls back to the default smolagents search engine if SearXNG is not configured.

**Q: How much does SearXNG cost?**
A: SearXNG is completely free and open source. You only pay for server hosting if you deploy it publicly.

**Q: Can I use SearXNG for commercial projects?**
A: Yes, SearXNG is licensed under AGPLv3, which allows commercial use.

**Q: Is SearXNG faster than search APIs?**
A: For local instances, yes! No network latency and results are cached in Redis.

**Q: Can SearXNG be used by multiple applications?**
A: Yes! Multiple applications can connect to the same SearXNG instance.

---

If you encounter any issues not covered here, please open an issue on the project repository.
