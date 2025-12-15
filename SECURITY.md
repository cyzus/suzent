# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

### Do Not
- **Do not** open a public GitHub issue
- **Do not** disclose the vulnerability publicly until it has been addressed

### Do
1. Email security details to: [your-email] (Update this with actual contact)
2. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### Response Timeline
- **24 hours**: Initial response acknowledging receipt
- **7 days**: Assessment and preliminary fix
- **30 days**: Patch released (target)

## Security Best Practices

### For Users

1. **API Keys**: Never commit API keys to version control
   - Use `.env` file (gitignored)
   - Rotate keys regularly
   - Use separate keys for dev/prod

2. **Access Control**: 
   - Run behind a reverse proxy (nginx, Caddy)
   - Implement authentication if exposing publicly
   - Use HTTPS in production

3. **Database**:
   - Regular backups
   - Secure PostgreSQL with strong passwords
   - Limit network access to database

4. **Dependencies**:
   - Keep dependencies updated
   - Review security advisories
   - Use `uv` to manage Python dependencies

### For Developers

1. **Input Validation**:
   - Sanitize all user inputs
   - Validate file uploads
   - Check path traversal in file operations

2. **SQL Injection**:
   - Use parameterized queries (already implemented)
   - Never concatenate user input into SQL

3. **XSS Prevention**:
   - Frontend uses `rehype-sanitize` (already implemented)
   - Validate markdown content
   - Escape HTML in user-generated content

4. **CORS**:
   - Configure allowed origins in production
   - Don't use `allow_origins=["*"]` in production

5. **Rate Limiting**:
   - Implement rate limiting for APIs
   - Prevent abuse of expensive operations

## Known Security Considerations

### Current Implementation

1. **No Built-in Authentication**: 
   - Currently designed for local/trusted use
   - Add authentication layer if exposing to internet
   - Consider OAuth, JWT, or API keys

2. **CORS Configuration**:
   - Development mode allows all origins
   - Must configure for production

3. **File Operations**:
   - FileTool has path restrictions
   - Review before enabling in untrusted environments

4. **Memory System**:
   - PostgreSQL credentials in environment
   - Use strong passwords
   - Network isolation recommended

### Recommendations for Production

```python
# Example: Add authentication middleware
from starlette.middleware.authentication import AuthenticationMiddleware

# Configure CORS properly
Middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Add rate limiting
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)
```

## Security Features

### Implemented
- ✅ SQL injection protection (parameterized queries)
- ✅ XSS prevention (content sanitization)
- ✅ Input validation
- ✅ Secure password handling (not stored in plain text)
- ✅ Path traversal protection in FileTool
- ✅ HTTPS support (via reverse proxy)

### Planned
- ⏳ API authentication
- ⏳ Rate limiting
- ⏳ Request size limits
- ⏳ CSRF protection
- ⏳ Security headers

## Dependencies

We use:
- **uv** for Python dependency management (fast, secure)
- **npm** for frontend dependencies
- Regular security updates
- Automated vulnerability scanning (GitHub Dependabot)

## Disclosure Policy

Once a vulnerability is fixed:
1. Security advisory published
2. CVE requested if applicable
3. Release notes include security fixes
4. Credit given to reporter (if desired)

## Questions?

For security-related questions that aren't vulnerabilities:
- Open a GitHub Discussion
- Check documentation first

---

Last Updated: 2024-12-15
