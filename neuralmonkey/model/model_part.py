"""Basic functionality of all model parts."""

from abc import ABCMeta
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Set, Tuple

import tensorflow as tf

from neuralmonkey.dataset import Dataset
from neuralmonkey.logging import log
from neuralmonkey import tf_utils

# pylint: disable=invalid-name
FeedDict = Dict[tf.Tensor, Any]
InitializerSpecs = List[Tuple[str, Callable]]
# pylint: disable=invalid-name


class ModelPart(metaclass=ABCMeta):
    """Base class of all model parts."""

    def __init__(self,
                 name: str,
                 reuse: "ModelPart" = None,
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
                    tf_utils.update_initializers(
                        (scope.name + "/" + name, initializer)
                        for name, initializer in initializers)

        with self.use_scope():
            self.train_mode = tf.placeholder(tf.bool, [], "train_mode")
            self.batch_size = tf.placeholder(tf.int32, [], "batch_size")

    @property
    def name(self) -> str:
        """Get the name of the model part and its variable scope."""
        return self._name

    @contextmanager
    def use_scope(self):
        """Return a context manager.

        Return a context manager that (re)opens the model part's variable
        and name scope.
        """
        # If we are already reusing, reuse regardless of self._reuse.
        reuse = self._variable_scope.reuse or self._reuse

        with tf.variable_scope(self._variable_scope, reuse=reuse):
            # tf.variable_scope always creates a NEW name scope for ops, but
            # we want to use the original one:
            with tf.name_scope(self._variable_scope.original_name_scope):
                yield

    def get_dependencies(self) -> Set["ModelPart"]:
        """Collect recusively all encoders and decoders."""
        to_return = set([self])

        if hasattr(self, "attentions"):
            to_return = to_return.union(
                *(enc.get_dependencies()
                  for enc in getattr(self, "attentions")
                  if isinstance(enc, ModelPart)))

        if hasattr(self, "encoders"):
            to_return = to_return.union(
                *(enc.get_dependencies()
                  for enc in getattr(self, "encoders")
                  if isinstance(enc, ModelPart)))

        if hasattr(self, "encoder"):
            enc = getattr(self, "encoder")
            if isinstance(enc, ModelPart):
                to_return = to_return.union(enc.get_dependencies())

        if hasattr(self, "input_sequence"):
            inpseq = getattr(self, "input_sequence")
            if isinstance(inpseq, ModelPart):
                to_return = to_return.union(inpseq.get_dependencies())

        if hasattr(self, "parent_decoder"):
            dec = getattr(self, "parent_decoder")
            if isinstance(dec, ModelPart):
                to_return = to_return.union(dec.get_dependencies())

        return to_return

    def feed_dict(self, dataset: Dataset, train: bool) -> FeedDict:
        fd = {}  # type: FeedDict
        fd[self.train_mode] = train
        fd[self.batch_size] = len(dataset)
        return fd

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
