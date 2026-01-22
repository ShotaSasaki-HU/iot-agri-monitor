cd mosquitto/certs

# 1. 自分たちだけの認証局 (CA) を作成
openssl genrsa -out ca.key 2048
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 -out ca.crt -subj "/CN=IoT_Root_CA"

# 2. サーバ証明書（Broker用）を作成
# Docker内のコンテナ名 "mosquitto" に対して発行
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "/CN=mosquitto"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365 -sha256

# 3. クライアント証明書（Telegraf用）を作成
# Subscriberもクライアントの一種なので証明書が必要
openssl genrsa -out telegraf.key 2048
openssl req -new -key telegraf.key -out telegraf.csr -subj "/CN=telegraf_subscriber"
openssl x509 -req -in telegraf.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out telegraf.crt -days 365 -sha256

# 4. クライアント証明書 （Publisher）を作成
openssl genrsa -out publisher.key 2048
openssl req -new -key publisher.key -out publisher.csr -subj "/CN=raspi_publisher"
openssl x509 -req -in publisher.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out publisher.crt -days 365 -sha256

# 権限変更 (読み取りエラー防止)
chmod 644 *.key *.crt

# 元のフォルダに戻る
cd ../..
