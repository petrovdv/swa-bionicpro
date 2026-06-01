FROM confluentinc/cp-kafka-connect:7.5.0

ENV DEBEZIUM_VERSION=2.4.1.Final
RUN mkdir -p /usr/share/confluent-hub-components/debezium-postgresql && \
    curl -fSL https://repo1.maven.org/maven2/io/debezium/debezium-connector-postgres/${DEBEZIUM_VERSION}/debezium-connector-postgres-${DEBEZIUM_VERSION}-plugin.tar.gz \
    | tar -xzf - -C /usr/share/confluent-hub-components/debezium-postgresql --strip-components=1 && \
    echo "Debezium connector installed successfully"