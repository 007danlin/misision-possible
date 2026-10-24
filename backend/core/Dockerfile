FROM golang:1.27.1-alpine AS builder
WORKDIR /core
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -o core

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /core/core .
EXPOSE 8081
CMD ["./core"]
