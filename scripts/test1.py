from collections import deque

queue = deque()
for i in range(5):
    queue.append(i)
    
print(queue.popleft())