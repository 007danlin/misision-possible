FROM golang:1.27.1-alpine AS builder
WORKDIR /chat
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o chat


FROM alpine:3.19
WORKDIR /app
COPY --from=builder /chat/chat .
EXPOSE 8088
CMD ["./chat"]
