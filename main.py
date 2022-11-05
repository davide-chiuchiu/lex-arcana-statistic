from itertools import chain, combinations_with_replacement
from typing import Optional

import matplotlib.pyplot as plt
import numpy
import pandas
import seaborn
from sklearn.metrics import mean_absolute_error


def dice_from(dice_types: list[int]) -> list[list[int]]:
    one_die = combinations_with_replacement(dice_types, 1)
    two_dice = combinations_with_replacement(dice_types, 2)
    three_dice = combinations_with_replacement(dice_types, 3)
    return [[dice] if isinstance(dice, int) else sorted(list(dice)) for dice in chain(one_die, two_dice, three_dice)]


def throw_dice(dice: list[int], shape: tuple[int]):
    return numpy.sum(numpy.stack([numpy.random.randint(1, die + 1, shape) for die in dice], axis=1), axis=1)


def throw_dice_with_fate(dice: list[int],
                         results: Optional[numpy.ndarray] = None) -> numpy.ndarray:
    throws = throw_dice(dice, results.shape)
    mask = (numpy.mod(results, sum(dice)) == 0).astype(int)
    results = (results + mask * throws).astype(int)

    if numpy.all(numpy.mod(results, sum(dice)) != 0):
        return results
    else:
        return throw_dice_with_fate(dice, results)


def success_probabilities_from(dice: list[int], n_events: int = int(1E6)):
    fate = throw_dice_with_fate(dice, numpy.zeros((n_events,)))

    bin_edges = [0, 3, 6, 9, 12, 15, 18, numpy.inf]
    labels = ['simple', 'normal', 'challenge', 'difficult', 'very difficult', 'extreme']

    counts = numpy.histogram(fate, bins=bin_edges)
    return pandas.Series(numpy.flipud(numpy.cumsum(numpy.flipud(counts[0] / n_events)))[1:],
                         index=labels,
                         name='success_probability')


def all_success_probabilities_from(dice: list[list[int]], n_events: int = int(1E6)) -> pandas.DataFrame:
    n_dice = [len(i) for i in dice]
    pd = [sum(dice_combo) for dice_combo in dice]
    enhanced_dices = pandas.DataFrame({'pd': pd, 'dice': dice, 'n_dice': n_dice})
    enhanced_dices = enhanced_dices[enhanced_dices['pd'] <= 25].sort_values(['pd', 'n_dice'], ignore_index=True)
    distributions = enhanced_dices.apply(lambda x: success_probabilities_from(x['dice'], n_events), axis=1)
    return pandas.concat([enhanced_dices, distributions], axis=1)


def max_probability_and_dice_from(probabilities: pandas.DataFrame) -> pandas.DataFrame:
    return probabilities.loc[probabilities.loc[:, 'probability'].idxmax(), ['dice', 'probability']]


def optimal_dice_throw_from(probabilities: pandas.DataFrame) -> pandas.DataFrame:
    inner_probabilities = probabilities.sort_values('pd')
    is_increasing = inner_probabilities['probability'].diff().ge(0, fill_value=0)

    if is_increasing.all():
        return inner_probabilities
    else:
        inner_probabilities.loc[~is_increasing, ['dice', 'probability']] = numpy.nan
        inner_probabilities.loc[:, ['dice', 'probability']] = \
            inner_probabilities.loc[:, ['dice', 'probability']].fillna(method='ffill')
        return optimal_dice_throw_from(inner_probabilities)


def dice_string_format_from(dice: list[int]) -> str:
    dice_count = pandas.Series(dice).value_counts()
    return (dice_count.astype(str) + 'd' + dice_count.index.astype(str)).str.cat(sep='+')


def to_long_format(success_probabilities: pandas.DataFrame) -> pandas.DataFrame:
    id_vars = ['pd', 'dice']
    value_vars = [col for col in success_probabilities.columns if col not in id_vars + ['n_dice']]
    success_probabilities_long = success_probabilities \
        .melt(id_vars=id_vars,
              value_vars=value_vars,
              var_name='difficulty',
              value_name='probability')
    return success_probabilities_long


def optimal_success_probabilities_from(success_probabilities: pandas.DataFrame) -> pandas.DataFrame:
    optimal_success_probabilities = success_probabilities \
        .groupby(['pd', 'difficulty'], as_index=False) \
        .apply(max_probability_and_dice_from) \
        .groupby('difficulty', as_index=False) \
        .apply(optimal_dice_throw_from)
    return optimal_success_probabilities


def cleaning_for_plotting(success_probabilities: pandas.DataFrame) -> pandas.DataFrame:
    inner_success_probabilities = success_probabilities[success_probabilities['probability'] >= 0.025]
    inner_success_probabilities['dice_string'] = inner_success_probabilities['dice'].apply(dice_string_format_from)
    inner_success_probabilities.loc[inner_success_probabilities['probability'] > 0.99, 'dice_string'] = 'any'
    return inner_success_probabilities


def plot_from(success_probabilities: pandas.DataFrame):
    success_probabilities_clean = cleaning_for_plotting(success_probabilities)

    figure = plt.figure(figsize=(20, 10))
    plot = seaborn.lineplot(x='pd',
                            y='probability',
                            data=success_probabilities_clean,
                            hue='difficulty',
                            marker='o',
                            alpha=0.3)
    plot.set_xticks(range(3, 26))
    plot.set_yticks(numpy.arange(0, 1, 0.1))

    for line in success_probabilities_clean.index:
        plot.text(success_probabilities_clean.pd[line], success_probabilities_clean.probability[line],
                  success_probabilities_clean.dice_string[line], horizontalalignment='center',
                  size='x-small', color='black')
    plt.show()


def compare_strategies(strategy_x: pandas.DataFrame, strategy_y: pandas.DataFrame) -> tuple[pandas.DataFrame, float]:
    comparison_fields = ['pd', 'difficulty', 'probability']
    comparison = pandas.merge(strategy_x[comparison_fields],
                              strategy_y[comparison_fields],
                              on=['pd', 'difficulty'],
                              how='left') \
        .fillna(method='ffill') \
        .groupby('difficulty').apply(lambda x: mean_absolute_error(x['probability_x'], x['probability_y']))
    return comparison, comparison.mean()


def lazy_strategy_from(success_probabilities: pandas.DataFrame,
                       optimal_success_probabilities: pandas.DataFrame) -> pandas.DataFrame:
    all_probabilities = pandas.merge(success_probabilities,
                                     optimal_success_probabilities.drop('dice', axis=1),
                                     on=['pd', 'difficulty'],
                                     how='left', suffixes=('', '_optimal'))
    all_probabilities['dice'] = all_probabilities['dice'].apply(dice_string_format_from)
    mae_by_pd_and_dice = all_probabilities \
        .groupby(['pd', 'dice'], as_index=False) \
        .apply(lambda x: mean_absolute_error(x['probability'], x['probability_optimal'])) \
        .rename(columns={None: 'mae'})
    return mae_by_pd_and_dice.groupby('pd', as_index=False).apply(lambda x: x.loc[x['mae'].idxmax(), :])


def lexarcana_statistic():
    dice_types = [3, 4, 5, 6, 8, 10, 12, 20]
    dice = dice_from(dice_types)

    n_events = int(1E6)
    success_probabilities = to_long_format(all_success_probabilities_from(dice, n_events))
    optimal_success_probabilities = optimal_success_probabilities_from(success_probabilities)
    plot_from(optimal_success_probabilities)

    lazy_strategy = lazy_strategy_from(success_probabilities, optimal_success_probabilities)

    print('Optimal strategy:\n')
    print(lazy_strategy.loc[:, ['pd', 'dice']])
    print(f'\nLoss of success probability from optimal strategy: {lazy_strategy["mae"].describe()}')
    return


if __name__ == '__main__':
    lexarcana_statistic()
