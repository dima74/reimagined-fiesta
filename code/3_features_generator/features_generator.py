import matplotlib
from tqdm import tqdm
matplotlib.use('TkAgg')

import numpy as np
import scipy.stats as sps
import matplotlib.pyplot as plt
import pandas as pd
import itertools
import collections
import pickle
import math

np.set_printoptions(linewidth=10 ** 7)
pd.set_option('display.width', None)
plt.rcParams['figure.figsize'] = (10, 7)

# def read_data(filename):
#     """
#     :return: (X, y, X_skeleton)
#         X.shape == (N, 28*28)
#         y.shape == (N)
#         X_skeleton.shape == (N, 8 * number_edges)
#             X_skeleton == [edge1, edge2, ...]
#             edge == node1, node2
#             node == x, y, degree, radial
#     """
#     with open(filename, 'rb') as input:
#         data = pickle.load(input)
#         X, y, X_skeleton = data['data'], data['labels'], data['skel_features']
#         return X, y, X_skeleton

# for debug only, pretty print skeleton
def pps(skeleton):
    result = []
    for i in range(0, len(skeleton), 8):
        node0 = skeleton[i + 4 * 0:i + 4 * 1]
        node1 = skeleton[i + 4 * 1:i + 4 * 2]
        result.append((node0, node1))
    return result


# q = 0
def convert_skeleton(skeleton):
    # global q
    # print(q)
    # q += 1
    """
    :return: (nodes, edges)
        nodes: [(x, y, degree, radial)]
        adjacency_list: массив массивов (adjacency_list[i] --- список вершин, смежных с i)
    """

    nodes = []
    # description == (x, y, degree, radial)
    descriptions_to_nodes = {}
    def convert_node(node):
        """ получает вершину в виде (x, y, degree, radial), сохраняет её в список вершин и возвращает индекс этой ввершины """
        x, y, degree, radial = node
        # node_description = tuple(node)
        node_description = (x, y)
        if node_description in descriptions_to_nodes:
            return descriptions_to_nodes[node_description]
        else:
            node_index = len(nodes)
            nodes.append(node)
            descriptions_to_nodes[node_description] = node_index
            return node_index

    edges = []
    for i in range(0, len(skeleton), 8):
        node0 = convert_node(skeleton[i + 4 * 0:i + 4 * 1])
        node1 = convert_node(skeleton[i + 4 * 1:i + 4 * 2])
        if node0 != node1:
            edges.append((node0, node1))

    adjacency_list = [[] for _ in range(len(nodes))]
    for node0, node1 in edges:
        adjacency_list[node0].append(node1)
        adjacency_list[node1].append(node0)

    # некоторая отладка для изучения того, почему записанноая степень вершины отличается от актуально
    # можно удалить это
    for node_index, node in enumerate(nodes):
        if node[2] != len(adjacency_list[node_index]):
            # print()
            # print(node_index, node, adjacency_list[node_index])
            # for node_neighbour in adjacency_list[node_index]:
            #     print(node_neighbour, nodes[node_neighbour])
            # вернуть идентификацию вершин только по координатам
            # import sys
            # sys.path.insert(0, '/home/dima/6science/MyFirstScientificPublication/code')
            from visualization.visualization import draw_skeleton
            # draw_skeleton(nodes, adjacency_list)
        # assert node[2] == len(adjacency_list[node_index])

    return nodes, adjacency_list

# наличие вершины степени три
# 0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
# есть три:     3689abdeghmnpqABEFHPRTY
# нету:         01257cijlorsuvwyzCDGIJLMNOSUVWZ
# есть четыре:  4fktxKQX


# наличие циклов
# 0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
# есть:  04689abdgopqBDOPQR
# нету:  12357cefhijklmnrstuvwxyzACEFGHIJKLMNSTUVWXYZ

# площадь цикла
# 04689abdgopqBDOPQR
# большая:    0oDOQ
# маленькая:  4689abdgpqBPR

def generate_features(skeleton):
    """
    :return: (nodes_features, edges)
        nodes_features: [(feature1, feature2, ...)]
        edges: [(node1_index, node2_index)]
    """
    features_generator = FeaturesGenerator(skeleton)
    return features_generator.generate_features()


class FeaturesGenerator:
    def __init__(self, skeleton):
        nodes, adjacency_list = convert_skeleton(skeleton)
        self.nodes = np.array(nodes)
        self.adjacency_list = adjacency_list

    def generate_features(self):
        self.find_cycles()
        # self.find_straight_lines()
        self.calculate_one_degree_nodes_features()
        nodes_features = [self.generate_node_features(node_index, node_features0) for node_index, node_features0 in enumerate(self.nodes)]
        nodes_features = np.array(nodes_features)
        return nodes_features, self.adjacency_list

    ################################################
    # служебные функции

    def get_nodes_distance(self, node1, node2):
        x1, y1, _, _ = self.nodes[node1]
        x2, y2, _, _ = self.nodes[node2]
        delta_x = x1 - x2
        delta_y = y1 - y2
        return math.sqrt(delta_x * delta_x + delta_y * delta_y)

    def get_angle_between_edges(self, edge1, edge2):
        # угол между (u1, v1) и (u2, v2)
        u1, v1 = edge1
        u2, v2 = edge2
        def normalize_edge(u, v):
            x_u, y_u, _, _ = self.nodes[u]
            x_v, y_v, _, _ = self.nodes[v]
            delta_x = x_u - x_v
            delta_y = y_u - y_v
            delta_length = math.sqrt(delta_x * delta_x + delta_y * delta_y)
            return (delta_x / delta_length, delta_y / delta_length)
        x1, y1 = normalize_edge(u1, v1)
        x2, y2 = normalize_edge(u2, v2)
        dot_product = x1 * x2 + y1 * y2
        # https://stackoverflow.com/a/13849249/5812238
        return math.acos(np.clip(dot_product, -1, +1))

    ################################################
    # методы для всего графа

    def calculate_one_degree_nodes_features(self):
        # кратчайшее расстояние для каждой вершины от неё до вершины степени один
        # (Дейкстра с начальными вершинами --- всеми вершинами степени 1)

        # и сумма углов поворота между рёбрами на пути от каждой вершины к ближайшей вершине степени один
        # (запоминаем путь в Дейкстре)

        from heapq import heappush, heappop
        queue = []  # [(distance, node, previous)]
        distances = [None] * len(self.nodes)
        previous_nodes = [None] * len(self.nodes)
        for node in range(len(self.nodes)):
            if len(self.adjacency_list[node]) == 1:
                heappush(queue, [0, node, -1])
        while len(queue) > 0:
            distance, node, previous_node = heappop(queue)
            if distances[node] is None:
                distances[node] = distance
                previous_nodes[node] = previous_node
                for neighbour in self.adjacency_list[node]:
                    if distances[neighbour] is None:
                        distance_new = distance + self.get_nodes_distance(node, neighbour)
                        heappush(queue, [distance_new, neighbour, node])
        self.distances_to_one_degree_node = distances

        angles_sum_on_path_one_degree_node = [None] * len(self.nodes)
        def update_angle(node):
            # возвращает пару (сумма_углов, предыдущая_вершина)
            previous_node = previous_nodes[node]
            assert previous_node is not None
            angles_sum = angles_sum_on_path_one_degree_node[node]
            if angles_sum is None:
                if previous_node == -1:
                    # вершина степени один
                    angles_sum = 0
                else:
                    previous_angles_sum, node1 = update_angle(previous_node)
                    node2 = previous_node
                    node3 = node
                    angles_sum = previous_angles_sum + self.get_angle_between_edges((node1, node2), (node2, node3))
            angles_sum_on_path_one_degree_node[node] = angles_sum
            return angles_sum, previous_node
        for node in range(len(self.nodes)):
            update_angle(node)
        self.angles_sum_on_path_one_degree_node = angles_sum_on_path_one_degree_node
        print(angles_sum_on_path_one_degree_node)

    def find_cycles(self):
        # поиск цикла (ищем только первый цикл, так как больше одного цикла почти не бывает (толко у цифры 8))
        cycle = None
        visited = np.zeros(len(self.nodes), dtype=np.bool)
        def dfs(node, previous_node):
            global cycle
            """
            :param node: текущая вершина dfs
            :param previous_node: предыдущая вершина dfs
            :return: (dfs_state, node)
                dfs_state:
                    0 --- цикл не найден
                    1 --- цикл найден, заполняем массив цикла
                    2 --- цикл найден, массив цикла заполнен 
                node --- вершина на которой dfs нашёл цикл
            """
            if visited[node]:
                # нашли цикл
                cycle = [node]
                return 1, node
            visited[node] = True
            for neighbour in self.adjacency_list[node]:
                if neighbour != previous_node:
                    dfs_state, cycle_node = dfs(neighbour, node)
                    if dfs_state == 1:
                        if node == cycle_node:
                            return 2, None
                        else:
                            cycle.append(node)
                            return 1, cycle_node
                    elif dfs_state == 2:
                        return 2, None
            return 0, None
        dfs(0, -1)
        self.cycle = cycle

        # площадь цикла
        if cycle is None:
            self.cycle_area = 0
        else:
            x, y = self.nodes[0:2, cycle].T
            # https://stackoverflow.com/a/30408825/5812238
            self.cycle_area = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))

    ################################################
    # методы для одной вершины

    def generate_node_features(self, node, node_features0):
        """
        features:
            degree --- степень вершины, от 1 до 3
            radial --- значение радиальной функции в вершине
            min_angle --- значение минимального угла между рёбрами, выходящими из вершины
            number_cycles --- число циклов, в которых содержится вершина (по сути это бинарное свойство, так как два цикла только у цифры 8)
            circle_area --- площадь области, ограниченной циклом. среднее площадей, если циклов несколько
            distance_to_one_degree_node --- минимальное расстояние до вершины степени 1
        """
        x, y, degree, radial = node_features0
        # TODO посмотреть как же так получается что степени вершин не совпадают
        # assert degree == len(adjacency_list[node])
        degree = len(self.adjacency_list[node])
        assert 0 <= degree <= 4, 'неожиданная степень вершины: {}'.format(degree)

        node_features = []
        node_features += [degree]
        node_features += [radial]
        node_features += [self.node_min_angle(node, x, y, degree, radial)]
        node_features += self.node_cycles_features(node, x, y, degree, radial)
        node_features += [self.one_degree_node_features(node, x, y, degree, radial)]

        # сумма углов поворота между рёбрами на пути к ближайшей вершине степени один
        # длина максимальной прямой линии, в которой содержится текущая вершина (прямая линия — путь в графе, такой что угол между каждой парой соседних рёбер отличается не более чем на 10 от 180)
        # наличие вершин степени 4 (полезно, применимо к только 2(?) символам, неосуществимо при текущем алгоритме ([хотя мб считать две очень близких вершины степени 3 как вершину степени 4))
        # число связных компонент
        return node_features


    def node_min_angle(self, node, x, y, degree, radial):
        def angle_between_neighbours(neighbour1, neighbour2):
            neighbour1 = self.adjacency_list[node][neighbour1]
            neighbour2 = self.adjacency_list[node][neighbour2]
            return abs(self.get_angle_between_edges((node, neighbour1), (node, neighbour2)))
        if degree == 1:
            min_angle = 0
        elif degree == 2:
            min_angle = angle_between_neighbours(0, 1)
        elif degree == 3:
            min_angle = min(angle_between_neighbours(0, 1), angle_between_neighbours(1, 2), angle_between_neighbours(2, 0))
        elif degree == 4:
            # изображений с вершинами степени 4 не так много...
            min_angle = math.pi / 4
        elif degree == 0:
            min_angle = 0
        else:
            assert False
        return min_angle

    def node_cycles_features(self, node, x, y, degree, radial):
        # number_cycles & cycle_area
        if (self.cycle is not None) and (node in self.cycle):
            node_number_cycles = 1
            node_cycle_area = self.cycle_area
        else:
            node_number_cycles = 0
            node_cycle_area = 0
        return [node_number_cycles, node_cycle_area]

    def one_degree_node_features(self, node, x, y, degree, radial):
        # минимальное расстояние до вершины степени 1
        return self.distances_to_one_degree_node[node]


skeletons = np.load('single_skeleton.npy')
# skeletons = np.load('../2_skeleton_creator/skeletons.npy')
# features = list(map(generate_features, tqdm(skeletons)))
features = list(map(generate_features, skeletons))
result = {
    'F': [
        {
            'nodes_features': nodes_features,
            'adjacency_list': adjacency_list
        } for nodes_features, adjacency_list in features
    ]
}

with open('features.pickle', 'wb') as output:
    pickle.dump(result, output)

# with open('single-image.pickle', 'rb') as input:
#     data = pickle.load(input)
#     x, x_skeleton = data['x'], data['x_skeleton']
#
# x_new = generate_features(x_skeleton)
# print(x_new)