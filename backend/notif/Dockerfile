FROM golang:1.27.1-alpine AS builder
WORKDIR /notif
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -o notif

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /notif/notif .
CMD ["./notif"]
