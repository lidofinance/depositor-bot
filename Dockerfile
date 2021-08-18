FROM python:3.9
WORKDIR .

ENV WEB3_INFURA_PROJECT_ID='b11919ed73094499a35d1b3fa338322a'
ENV ACCOUNT_PRIVATE_KEY='99e0d92b43a5b3c2311acafad1cef6a07e9098060067a0f8fd1f500fe9fc7bba'

COPY . .
RUN pip install -r requirements.txt

CMD ["brownie", "run", "depositor", "--network=mainnet"]
