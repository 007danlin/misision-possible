FROM golang:1.27.3-alpine@sha256:d200d2dd76b03a99b52651fd1325aff7dcd35422c35c01bac56571b0507f3deb AS builder
WORKDIR /core
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -o core

FROM alpine:3.19@sha256:6baf43584bcb78f2e5847d1de515f23499913ac9f12bdf834811a3145eb11ca1
WORKDIR /app
RUN addgroup -g 10001 app && adduser -D -u 10001 -G app app \
    && mkdir -p /app/data/trips && chown -R app:app /app/data
COPY --from=builder /core/core .
USER app
EXPOSE 8080
CMD ["./core"]
