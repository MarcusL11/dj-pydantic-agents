"""Django test case classes with unittest-parametrize support.

Choose the fastest class that a test needs. Each class keeps the database
behaviour of its Django class and adds the @parametrize decorator.
"""

from django import test
from unittest_parametrize import ParametrizedTestCase


class SimpleTestCase(ParametrizedTestCase, test.SimpleTestCase):
    """Block database access."""


class TestCase(SimpleTestCase, test.TestCase):
    """Roll back the database changes of each test."""


class TransactionTestCase(SimpleTestCase, test.TransactionTestCase):
    """Commit real transactions and flush the tables after each test."""
