FROM golang:1.24.8-bookworm AS build

RUN mkdir -p /out && \
    GOBIN=/out go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install --no-install-recommends -y ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 10003 minio

COPY --from=build /out/minio /usr/local/bin/minio

USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
