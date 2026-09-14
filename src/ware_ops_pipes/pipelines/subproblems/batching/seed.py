from ware_ops_algos.algorithms import SeedBatching
from ware_ops_algos.algorithms.batching.component_registry import (
    SEED_CRITERIA,
    SIMILARITY_MEASURES,
)
from ware_ops_algos.domain_models import Resources, LayoutData, Articles
from ware_ops_pipes.pipelines.templates.cosy_template import MultiOrderBatching
from ware_ops_pipes.pipelines.io_helpers import load_pickle


class ClosestDepotMinDistanceSeedBatching(MultiOrderBatching):
    abstract = False
    algo_cls =  SeedBatching

    seed_criterion_name = "CLOSEST_TO_DEPOT"
    similarity_measure_name = "MIN_DISTANCE"

    def config_fingerprint_payload(self) -> dict:
        return {
            "seed_criterion": self.seed_criterion_name,
            "similarity_measure": self.similarity_measure_name,
        }

    def get_inited_batcher(self):
        articles: Articles = load_pickle(self.input()["instance"]["articles"].path)
        resources: Resources = load_pickle(self.input()["instance"]["resources"].path)
        layout: LayoutData = load_pickle(self.input()["instance"]["layout"].path)
        layout_network = layout.layout_network
        batcher = SeedBatching(
            pick_cart=resources.resources[0].pick_cart,
            articles=articles,
            seed_criterion=SEED_CRITERIA[self.seed_criterion_name](
                distance_matrix=layout_network.distance_matrix,
                start_node=layout_network.start_node,
            ),
            similarity_measure=SIMILARITY_MEASURES[self.similarity_measure_name](
                distance_matrix=layout_network.distance_matrix,
            ),
        )
        return batcher

