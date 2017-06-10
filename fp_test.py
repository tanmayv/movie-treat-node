from fp_growth import find_frequent_itemsets
transaction = []
minsup = 2;
transactions = [[1, 2, 5],
                [2, 4],
                [2, 3],
                [1, 2, 4],
                [1, 3],
                [2, 3],
                [1, 3],
                [1, 2, 3, 5],
                [1, 2, 3]]
for itemset in find_frequent_itemsets(transactions, minsup):
    print itemset
