# Docker

![Docker](https://img.shields.io/badge/Docker-Ready-blue?style=flat-square&logo=docker)
![Python](https://img.shields.io/badge/Python-3.9+-brightgreen?style=flat-square&logo=python)

## Overview

Distributed file synchronization system built using Docker and Python. This system allows multiple nodes (Docker containers) to automatically synchronize files within a shared directory across a local network. It's particularly useful for scenarios where consistent file states need to be maintained across different environments or machines without manual intervention.

## Tech Stack

- **Docker**: For containerizing the application and managing multiple nodes.
- **Python**: To handle file system events and synchronization logic.
- **Watchdog**: A Python library for monitoring file system events in real-time.
- **Socket Programming**: Used for communication between nodes.
- **Docker Compose**: Tool for defining and running multi-container Docker applications.

## Prerequisites

- **Docker**: Ensure Docker is installed on your system. You can download it from [here](https://www.docker.com/get-started).
- **Python 3.9+**: Make sure Python 3.9 or higher is installed. Check it [here](https://www.python.org/downloads/).

## Installation

1. Clone the repository

2. Build and start the containers
    ```
    docker-compose up --build
    ```
    
![image](https://github.com/user-attachments/assets/3057d745-72cd-4d36-87a7-5719e7cd818b)

3. Accessing the Containers
   
   ```
   docker exec -it <container_name> /bin/bash
   ```


## Project Structure

Your-repository-name/

│

├── Dockerfile          # Docker configuration for the application

├── docker-compose.yml  # Docker Compose configuration

├── node.py             # Python script managing file synchronization

├── README.md           # Project documentation

└── sync_dir/           # Directory where files are synced across nodes


## How It Works

1. **Dockerized Nodes**: Each node is a Docker container that listens for file changes in the sync_dir directory.
   
2. **File Synchronization**: Files added to any node's sync_dir are synchronized across all other nodes.
   
3. **Handling File Conflicts**: If a file with the same name already exists, the system generates a new file with a modified name.
   
![image](https://github.com/user-attachments/assets/9030171f-7260-44fc-9921-69c674fa2dd3)


