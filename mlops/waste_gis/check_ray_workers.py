import socket

import ray
import ray.train as train
from ray.train import ScalingConfig
from ray.train.torch import TorchTrainer


def worker_check():
    """
    This function is executed independently
    inside every Ray training worker.
    """

    context = train.get_context()

    rank = context.get_world_rank()
    world_size = context.get_world_size()

    print(
        f"rank={rank} "
        f"world_size={world_size} "
        f"host={socket.gethostname()}"
    )

    train.report(
        {
            "rank": rank,
            "world_size": world_size,
        }
    )


def main():

    print("Ray version:", ray.__version__)

    # ------------------------------------------------------
    # ScalingConfig tells Ray what resources the training
    # job needs.
    #
    # Here:
    #   2 worker processes
    #   CPU only
    #   1 CPU reserved per worker
    # ------------------------------------------------------

    scaling = ScalingConfig(
        num_workers=2,
        use_gpu=False,
        resources_per_worker={
            "CPU": 1,
        },
    )

    # ------------------------------------------------------
    # TorchTrainer tells Ray:
    #
    # "Run worker_check() as a distributed PyTorch job
    # using the worker topology described above."
    # ------------------------------------------------------

    trainer = TorchTrainer(
        train_loop_per_worker=worker_check,
        scaling_config=scaling,
    )

    result = trainer.fit()

    print()
    print("=== DRIVER RESULT ===")
    print(result.metrics)


if __name__ == "__main__":
    main()
