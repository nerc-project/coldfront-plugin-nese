# This Dockerfile uses a multi-stage build
# * The builder image installs the compile time dependencies and
#   installs the pip packages into a virtual environment.
# * The final image copies the virtual environment over and
#   installs netcat and mysql libraries as runtime deps.

# Builder Image
FROM python:3.9-slim-bullseye as builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential default-libmysqlclient-dev libpq-dev git && \
    apt-get clean -y

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# change here...
COPY coldfront-nerc/requirements.txt /tmp/requirements.txt
COPY coldfront-plugin-nese/requirements.txt /tmp/neserequirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN pip3 install -r /tmp/neserequirements.txt

FROM minio/mc:RELEASE.2022-02-16T05-54-01Z as minio

# Final Image
FROM python:3.9-slim-bullseye

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        netcat libmariadb3 libpq5 && \
    apt-get clean -y

COPY --from=builder --chown=1001:0 /opt/venv /opt/venv
COPY --from=minio /usr/bin/mc /usr/bin/mc
COPY --from=minio /licenses/CREDITS /licenses/CREDITS
COPY --from=minio /licenses/LICENSE /licenses/LICENSE

# # changed for nese plugin
COPY coldfront-plugin-nese/skaffold/local_settings.py /opt/venv/lib/python3.9/site-packages
COPY coldfront-plugin-nese/skaffold/run_coldfront.sh /opt/venv/bin
# ##

RUN mkdir /code /plugins
WORKDIR /code
COPY coldfront-plugin-nese/src /code

ENV PATH="/opt/venv/bin:$PATH"
ENV DJANGO_SETTINGS_MODULE="local_settings"
ENV DEBUG: "True"
ENV PYTHONUNBUFFERED: "1"
ENV PYTHONPATH: "/code:/plugins"

EXPOSE 8080

# USER 1001

CMD [ "run_coldfront.sh" ]
