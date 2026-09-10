---
type: decision
title: Infrastructure as Code - Terraform Pattern
category: Cloud Architecture & DevOps
status: active
created: 2026-08-28
source: hashicorp/terraform (Hamle 5)
tags: [terraform, iac, aws, cloud, infrastructure]
---

# Infrastructure as Code with Terraform

**Pattern:** Declarative Infrastructure Management

## Core Concept

```hcl
# main.tf
# Declare desired state, Terraform figures out how to get there

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
  
  tags = {
    Name = "web-server"
  }
}
```

## Variables and Outputs

```hcl
# variables.tf
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "instance_count" {
  description = "Number of instances"
  type        = number
  default     = 1
}

# outputs.tf
output "web_instance_ip" {
  value       = aws_instance.web.public_ip
  description = "Public IP of web server"
}
```

## State Management

```bash
# State file tracks deployed resources
terraform.tfstate   # Local state (single dev only)
terraform.tfvars    # Variable overrides

# Production: Use remote state
# terraform.tf
terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-lock"
    encrypt        = true
  }
}

# Prevents concurrent modifications (DynamoDB lock)
```

## Common Patterns

**1. Modules (Reusable Components)**
```hcl
# modules/vpc/main.tf
resource "aws_vpc" "main" {
  cidr_block = var.cidr_block
}

# main.tf
module "vpc" {
  source = "./modules/vpc"
  cidr_block = "10.0.0.0/16"
}

module "app" {
  source = "./modules/app"
  vpc_id = module.vpc.vpc_id
}
```

**2. Environments (Dev/Staging/Prod)**
```
infrastructure/
├── dev/
│   └── terraform.tfvars
├── staging/
│   └── terraform.tfvars
└── prod/
    └── terraform.tfvars
```

**3. Conditional Resources**
```hcl
resource "aws_db_instance" "main" {
  count = var.enable_rds ? 1 : 0
  # Only created if enable_rds = true
}
```

## Workflow

```bash
# 1. Initialize (download providers)
terraform init

# 2. Preview changes
terraform plan

# 3. Apply infrastructure
terraform apply

# 4. Destroy (cleanup)
terraform destroy
```

## Best Practices

```
✓ Version control terraform files (git)
✓ Use remote state + locking (S3 + DynamoDB)
✓ Use modules for reusability
✓ Separate variables per environment
✓ Use workspaces for multiple environments
✓ Run plan in CI before apply
✓ Never manually edit resources (terraform overwrite)
```

## Gotchas

```
❌ Storing secrets in variables
  ✓ Use AWS Secrets Manager or HashiCorp Vault

❌ Not using remote state
  ✓ Team can't collaborate safely

❌ Large state files (>100MB)
  ✓ Split into modules

❌ Destroying production accidentally
  ✓ Use terraform_remote_state + locks
```

---

**Bağlantılar:** [[hamle5-cloud-002-kubernetes-hpa]]
