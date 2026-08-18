"""消息队列中间件模块（基于 aio-pika 异步 RabbitMQ 客户端）。

模块职责：
    - connection: 管理 RabbitMQ 异步连接与通道（RobustConnection，自动重连）。
    - exchanges: 集中声明交换机（名称、类型、持久化等）。
    - queues: 集中声明队列及其与交换机的绑定关系。
    - producer: 生产者，负责发布消息到指定交换机。
    - consumer: 消费者基类，封装消息消费、ACK、异常处理流程。
    - consumers: 具体业务消费者实现目录。
    - runner: 消费者进程入口（main 函数），独立进程运行。

使用约定：
    - FastAPI 进程内只使用 Producer（通过依赖注入获取）。
    - 消费者单独进程运行：`python -m app.mq.runner`。
    - 所有 MQ 操作均为异步，禁止在异步函数中调用同步阻塞 IO。
"""
