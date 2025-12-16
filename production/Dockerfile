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

# Copy data files (PMTiles, etc.)
# Note: You should have generated these before building the image
COPY data/*.pmtiles /usr/share/nginx/html/data/ 2>/dev/null || true
COPY data/*.mbtiles /usr/share/nginx/html/data/ 2>/dev/null || true

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
