"""Recipe registry — maps visual types/keywords to prompt fragments."""

from app.agents.animation_v2.recipes import (
    array,
    matrix,
    tree,
    graph,
    linked_list,
    stack_queue,
    equation,
    coordinate,
    code,
    flowchart,
    neural_net,
    convolution,
    heatmap,
    comparison,
    arrow,
)

ALL_RECIPES = [
    array, matrix, tree, graph, linked_list, stack_queue,
    equation, coordinate, code, flowchart,
    neural_net, convolution, heatmap, comparison, arrow,
]

RECIPE_BY_ID = {r.ID: r for r in ALL_RECIPES}


def get_recipe(recipe_id: str):
    """Get a recipe module by its ID string."""
    return RECIPE_BY_ID.get(recipe_id)


def get_all_recipes():
    """Return all recipe modules."""
    return list(ALL_RECIPES)
