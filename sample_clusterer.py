"""
Sample program to show how to load the data and how to evaluate a (dummy) algorithm.
"""
import argparse
import arpi_evaluator
import numpy as np
import pandas as pd
import pickle
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import pairwise_distances

BEGINNING_OF_TIME = np.datetime64('1970-01-01T00:00:00')
TIMEDELTA_HOUR = np.timedelta64(1, 'h')


def main():
    # parse args
    parser = argparse.ArgumentParser("A sample program.")
    parser.add_argument("input_file", help="A pickle input file, e.g. aircan-data-split-clean.pkl.")
    parser.add_argument("output_file", help="An output file.")
    args = parser.parse_args()

    # read data; this will load the data as 6 pandas DataFrames, which allow fast manipulations and (slower) iterations
    # more info on pandas here: https://pandas.pydata.org/
    with open(args.input_file, 'rb') as fin:
        [defect_df_train, defect_df_dev, defect_df_test, ata_df, mel_df, trax_df] = pickle.load(fin)
        print(f"Read # samples: {len(defect_df_train)} train, {len(defect_df_test)} dev, {len(defect_df_test)} test.")

    # show a few things possible with the pandas data frames for those who are not familiar
    print(f"\nThere are {len(defect_df_train.columns)} columns in all 3 defect dataframes, whose names and types are:")
    print(defect_df_train.dtypes)
    print("\nThe first few rows for train are:")
    print(defect_df_train.head())
    print(f"\nThere are {len(defect_df_train.ac.unique())} unique aircrafts in train, "
          f"{len(defect_df_dev.ac.unique())} in dev and {len(defect_df_test.ac.unique())} in test.")

    # show how to find fields by integer indices or by id
    print(f"The 3rd defect for dev: {defect_df_dev.iloc[2]}")

    description_column_index = defect_df_dev.columns.get_loc('defect_description')
    print("The 3rd defect for dev (only text portion): "
          f"{defect_df_dev.iloc[2, description_column_index]}")

    print(f"\nLookup a defect by id (L-5747551-1), then field (ac): {defect_df_train.loc['L-5747551-1']['ac']}")
    print(f"Is the value L-5747551-1 present in train?: {'L-5747551-1' in defect_df_train.index}")
    print(f"Is the value L-5747551-1 present in dev?: {'L-5747551-1' in defect_df_test.index}")

    # print(defect_df_dev.info())  # also fun

    # show how a dummy clusterer can be evaluated and further shows how pandas can be used
    print("\nPredicting recurrence clusters...\n")
    test_predictions = find_recurrent_defects_naively(defect_df_test)

    print("\nEvaluation\n")
    score, eval_debug_info = arpi_evaluator.evaluate_recurrent_defects(defect_df_test, test_predictions)
    print(f"dummy_system v zero\t{score * 100}%\tThis system stinks!")

    print(f"Dumping debug info in file {args.output_file}")
    with open(args.output_file, 'wt', encoding='utf-8') as fout:
        arpi_evaluator.dump_debug_info(defect_df_test, eval_debug_info, fout)


def find_recurrent_defects_naively(defect_df):
    """
    Finds recurrent defects (naive algorithm to show how to proceed with the data).

    :param defect_df: The defect dataframe for which we try to find recurrent defects.
    :return: A result datastructure in the format expected for evaluation.
    """
    result = []

    # we regroup defects by aircraft ('ac') since a given defect cannot be recurrent across different aircraft
    grouped_by_ac = defect_df.groupby('ac')

    # we iterate over each aircraft group, with a tuple (name of aircraft, dataframe for all defects for this aircraft)
    for name, ac_group in grouped_by_ac:
        print(f"Aircraft {name} has {len(ac_group)} defects reported.")

        labels = []  # we prepare the labels for each defect, in the order we encounter them
        feature_matrix = np.zeros((len(ac_group), 2))  # we have only 2 features: chapter and timestamp, ofc improveable

        # we can then iterate over all rows of the data and use the fields we want!
        row_number = 0
        for _, row in ac_group.iterrows():  # index is the row number and row is the data itself
            cur_type = row['defect_type']  # e.g. C, E or L
            cur_defect = row['defect']  # an int
            cur_item = row['defect_item']  # an int

            cur_id = f'{cur_type}-{str(cur_defect)}-{str(cur_item)}'  # this uniquely identifies a defect
            labels.append(cur_id)  # for our clustering algorithm (below)

            if pd.notnull(row['chapter']):  # some values, like the ATA chapter here can be null (i.e. not available)
                cur_chapter = row['chapter']
            else:
                cur_chapter = -1

            cur_reported_date = row['reported_datetime']

            # we convert the date to hours
            cur_reported_hours = (cur_reported_date - BEGINNING_OF_TIME) // TIMEDELTA_HOUR

            # we add the features to the feature matrix
            feature_matrix[row_number] = (cur_chapter, cur_reported_hours)
            row_number += 1

        # our simple algorithm performs agglomerative clustering - this is not important, it's just a demo
        clustering_model = AgglomerativeClustering(n_clusters=None, affinity='precomputed',
                                                   distance_threshold=.1, linkage='average')
        dist_matrix = pairwise_distances(feature_matrix, feature_matrix, metric=custom_distance_fun)
        clusters = clustering_model.fit_predict(dist_matrix)

        # we convert the clusters array([192,  192, 1193, ...,  247,  247,  357]) into a result data structure
        cluster_map = {}  # a mapping from cluster name to list of defects
        for i, cluster_label in enumerate(clusters):
            cluster_map[cluster_label] = cluster_map.get(cluster_label, set())
            cluster_map[cluster_label].add(labels[i])

        ac_result = list(cluster_map.values())
        result += ac_result

    return result


def custom_distance_fun(defect1, defect2):
    """This returns a simple distance function in interval [0,1] between 2 defects."""
    distance = 1

    # first check if they are within 30 days of each other
    delta_days = abs(defect2[0] - defect1[0]) / 24
    if delta_days <= 30:  # 30 days for our example
        delta_chapter = 0 if defect1[1] == defect2[1] else 1
        distance = 0.3 * (delta_days / 30.0) + 0.7 * delta_chapter

    return distance


if __name__ == '__main__':
    main()
