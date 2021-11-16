FROM python:3.9 as builder

COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.9

WORKDIR /app

RUN groupadd -r user && useradd -r -g user user
RUN mkdir /home/user
RUN chown -R user:user /home/user

COPY --from=builder --chown=user:user /root/.local/ /usr/local
COPY --chown=user:user . .

USER user

EXPOSE 8080

ENV PATH=$PATH:/usr/local/bin
ENV PYTHONPATH="/usr/local/lib/python3.9/site-packages/"

HEALTHCHECK --interval=5m --timeout=3s CMD curl -f http://localhost:8080/ || exit 1
