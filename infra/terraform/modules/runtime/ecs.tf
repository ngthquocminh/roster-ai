# ECS cluster and the one-off migrate task (Story 6.2 D1, D10). The API and
# worker task definitions and services are Story 6.3's.

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix

  # D10's not-added list: no Container Insights.
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

locals {
  # Digest only, never a tag: the image that runs is exactly the one reviewed.
  backend_image = var.backend_image_digest == null ? null : "${aws_ecr_repository.backend.repository_url}@${var.backend_image_digest}"
}

# count = 0 until an image exists, so the first apply can create the
# repository the image is pushed to.
resource "aws_ecs_task_definition" "migrate" {
  count = var.backend_image_digest == null ? 0 : 1

  family                   = "${var.name_prefix}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution["migrate"].arn
  # No task_role_arn: the bootstrap calls no AWS API.

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "migrate"
      image     = local.backend_image
      essential = true
      command   = ["python", "-m", "scripts.bootstrap_hosted", "--require-tls"]
      environment = [
        { name = "SHIFTMIND_SEED_PLANNER_SUBJECT", value = var.planner_subject },
        { name = "SHIFTMIND_SEED_PLANNER_EMAIL", value = var.planner_email },
      ]
      secrets = [
        { name = "ROSTERAI_DATABASE_URL", valueFrom = var.database_url_secret_arn },
        { name = "ROSTERAI_PROVISIONING_DATABASE_URL", valueFrom = var.provisioning_database_url_secret_arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this["migrate"].name
          awslogs-region        = var.region
          awslogs-stream-prefix = "migrate"
        }
      }
    },
  ])
}
