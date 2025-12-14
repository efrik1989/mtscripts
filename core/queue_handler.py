import pandas as pd
import threading
import queue

data_queue = queue.Queue()

def set_data_to_queue(data):
    data_queue.put(data)

def set_data_to_frame():
    all_data = []
    while True:
        try:
            # Берем данные из очереди (с таймаутом, чтобы не зависнуть)
            item = data_queue.get(timeout=1)
            all_data.append(item)
            data_queue.task_done() # Сигнализируем, что задача выполнена
        except queue.Empty:
            break # Очередь пуста
    # Создаем DataFrame один раз в главном потоке
    df = pd.DataFrame(all_data)
    return df