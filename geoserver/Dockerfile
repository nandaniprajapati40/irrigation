FROM eclipse-temurin:17-jre-jammy

ENV GEOSERVER_VERSION=2.27.2
ENV GEOSERVER_HOME=/opt/geoserver
ENV GEOSERVER_DATA_DIR=/opt/geoserver/data_dir
ENV JAVA_OPTS="-Xms512m -Xmx4g"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    unzip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

RUN curl -L \
    "https://sourceforge.net/projects/geoserver/files/GeoServer/${GEOSERVER_VERSION}/geoserver-${GEOSERVER_VERSION}-bin.zip/download" \
    -o geoserver.zip && \
    mkdir -p /opt/geoserver && \
    unzip geoserver.zip -d /opt/geoserver && \
    rm -f geoserver.zip

WORKDIR /opt/geoserver

EXPOSE 8080

CMD ["sh", "-c", "exec java $JAVA_OPTS -DGEOSERVER_DATA_DIR=$GEOSERVER_DATA_DIR -jar start.jar jetty.http.host=0.0.0.0 jetty.http.port=8080"]