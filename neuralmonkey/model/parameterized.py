from abc import ABCMeta
from contextlib import contextmanager
from typing import List, Tuple, Callable, Iterator

import tensorflow as tf

from neuralmonkey.tf_utils import update_initializers
from neuralmonkey.logging import log

# pylint: enable=invalid-name
InitializerSpecs = List[Tuple[str, Callable]]
# pylint: disable=invalid-name


class Parameterized(metaclass=ABCMeta):

    def __init__(self,
                 name: str,
                 reuse: "Parameterized" = None,
                 save_checkpoint: str = None,
                 load_checkpoint: str = None,
                 initializers: InitializerSpecs = None) -> None:

        self._name = name
        self._save_checkpoint = save_checkpoint
        self._load_checkpoint = load_checkpoint

        self._saver = None  # type: tf.train.Saver
        self._reuse = reuse is not None

        if reuse is not None:
            # pylint: disable=unidiomatic-typecheck
            # Here we need an exact match of types
            if type(self) != type(reuse):
                raise TypeError("Can only reuse parameters of ModelPart "
                                "objects within the same sub-class.")
            # pylint: enable=unidiomatic-typecheck

            if initializers is not None:
                raise ValueError("Cannot use initializers in model part '{}' "
                                 "that reuses variables from '{}'."
                                 .format(name, reuse.name))

            # pylint: disable=protected-access
            self._variable_scope = reuse._variable_scope  # type: ignore
            # pylint: enable=protected-access
        else:
            with tf.variable_scope(name) as scope:
                self._variable_scope = scope
                if initializers is not None:
                    update_initializers((scope.name + "/" + name, initializer)
                                        for name, initializer in initializers)

    @property
    def name(self) -> str:
        """Get the name of the parameterized object and its variable scope."""
        return self._name

    @contextmanager
    def use_scope(self) -> Iterator[None]:
        """Return the object variable scope context manager.

        Return the context manager that (re)opens variable and name scopes of
        the parameterized object..
        """
        # If we are already reusing, reuse regardless of self._reuse.
        reuse = self._variable_scope.reuse or self._reuse

        with tf.variable_scope(self._variable_scope, reuse=reuse):
            # tf.variable_scope always creates a NEW name scope for ops, but
            # we want to use the original one:
            with tf.name_scope(self._variable_scope.original_name_scope):
                yield

    def _init_saver(self) -> None:
        if not self._saver:
            parts_variables = tf.get_collection(
                tf.GraphKeys.GLOBAL_VARIABLES, scope=self._variable_scope.name)

            with self.use_scope():
                self._saver = tf.train.Saver(var_list=parts_variables)

    def save(self, session: tf.Session) -> None:
        """Save model part to a checkpoint file."""
        if self._save_checkpoint:
            self._init_saver()
            self._saver.save(session, self._save_checkpoint)

            log("Variables of '{}' saved to '{}'".format(
                self.name, self._save_checkpoint))

    def load(self, session: tf.Session) -> None:
        """Load model part from a checkpoint file."""
        if self._load_checkpoint:
            self._init_saver()
            self._saver.restore(session, self._load_checkpoint)

            log("Variables of '{}' loaded from '{}'".format(
                self.name, self._load_checkpoint))
