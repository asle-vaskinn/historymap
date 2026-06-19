# Production Dockerfile for Trondheim Historical Map System
# Self-contained deployment with nginx serving static files

FROM nginx:alpine AS production

# Install curl for healthcheck
RUN apk add --no-cache curl

# Create necessary directories
RUN mkdir -p /usr/share/nginx/html/data

# Copy nginx configuration
COPY nginx.prod.conf /etc/nginx/conf.d/default.conf

# Copy frontend files
COPY frontend/index.html /usr/share/nginx/html/
COPY frontend/style.css /usr/share/nginx/html/
COPY frontend/app.js /usr/share/nginx/html/

# Data files (PMTiles) are NOT baked into the image. The canonical deploy is the
# native nginx tenant (scripts/setup_vps.sh + deploy_vps.sh); data is uploaded
# separately by scripts/sync_data.sh. The previous `COPY ... 2>/dev/null || true`
# lines here were invalid — Dockerfile COPY does not support shell redirection,
# so they never worked. Mount/sync data into /usr/share/nginx/html/data instead.

# Set proper permissions
RUN chmod -R 755 /usr/share/nginx/html && \
    chown -R nginx:nginx /usr/share/nginx/html

# Health check endpoint - nginx status
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Expose HTTP port
EXPOSE 80

# Start nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
