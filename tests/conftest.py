import pytest
from backend.data import Dataset
from backend.model import Model

@pytest.fixture(scope='session')
def dataset():
    return Dataset(__import__('pathlib').Path(__file__).resolve().parents[1] / 'dataPreprocess/rawData/australiar.csv')

@pytest.fixture(scope='session')
def model(dataset):
    return Model(dataset)
