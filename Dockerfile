FROM python:3.9
WORKDIR .

ENV WEB3_INFURA_PROJECT_ID='b11919ed73094499a35d1b3fa338322a'
ENV ACCOUNT_FILENAME='~/work/geth/data/keystore/key.json'
ENV ACCOUNT_PASSWORD='pswd'

COPY . .
RUN pip install -r requirements.txt

CMD ["brownie", "run", "depositor", "--network=mainnet"]
