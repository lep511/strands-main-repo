FROM public.ecr.aws/lambda/microvms:al2023-minimal AS builder

RUN dnf install -y gcc make openssl-devel && dnf clean all

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM public.ecr.aws/lambda/microvms:al2023-minimal

COPY --from=builder /build/target/release/microvm-rust /usr/local/bin/microvm-rust

EXPOSE 8080 8081 9000

CMD ["/usr/local/bin/microvm-rust"]
