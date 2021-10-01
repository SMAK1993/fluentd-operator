# fluentd-operator

## Description

The Fluentd Operator allows you to unify data collection and consumption for better use and understanding of data.

## Install Dependencies and Build

To build the charm, first install `charmcraft`,  `juju` and `microk8s`

    snap install charmcraft
    snap install juju --classic
    snap install microk8s --classic 

Then in this git repository run the command

    charmcraft pack

## Usage

    juju deploy ./fluentd-operator.charm \
        --resource fluentd-image=karimsye/custom-fluentd:latest

## Relate to Elasticsearch Operator Charm

    juju deploy elasticsearch-k8s
    juju add-relation elasticsearch-k8s fluentd-operator

## Developing

Create and activate a virtualenv with the development requirements:

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

The Python operator framework includes a very nice harness for testing
operator behaviour without full deployment. Just `run_tests`:

    ./run_tests
