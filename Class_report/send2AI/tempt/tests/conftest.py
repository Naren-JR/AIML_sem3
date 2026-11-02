import pytest
from backend.data import Dataset
from backend.model import Model

@pytest.fixture(scope='session')
def dataset():
    return Dataset()

@pytest.fixture(scope='session')
def model(dataset):
    return Model(dataset)
