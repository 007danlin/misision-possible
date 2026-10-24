FROM golang:1.27.1-alpine AS builder
ENV GOEXPERIMENT=runtimesecret
WORKDIR /auth
COPY . .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -o auth

FROM alpine:3.19
WORKDIR /app
COPY --from=builder /auth/auth .
EXPOSE 7574
CMD ["./auth"]
