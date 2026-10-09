# Offline proof of the GitHub OIDC deploy identity (Story 6.2 D9). Mock
# provider, no credentials. The live proof is backend-image.yml's two jobs: the
# environment job assumes the role and pushes, the job without the environment
# is refused.
mock_provider "aws" {
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    }
  }
}

variables {
  name_prefix            = "shiftmind-test"
  github_repository      = "example-owner/example-repo"
  github_environment     = "portfolio"
  backend_repository_arn = "arn:aws:ecr:ap-southeast-1:111122223333:repository/shiftmind-test-backend"
}

run "trust_is_exact_on_aud_and_sub" {
  command = apply

  assert {
    condition = jsondecode(aws_iam_role.deploy.assume_role_policy) == {
      Version = "2012-10-17"
      Statement = [{
        Effect    = "Allow"
        Principal = { Federated = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com" }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = "repo:example-owner/example-repo:environment:portfolio"
          }
        }
      }]
    }
    error_message = "The trust must be StringEquals on aud and on the exact environment-scoped sub, and nothing else."
  }

  assert {
    condition     = !strcontains(aws_iam_role.deploy.assume_role_policy, "StringLike") && !strcontains(aws_iam_role.deploy.assume_role_policy, "*")
    error_message = "No StringLike and no wildcard anywhere in the trust."
  }

  assert {
    condition     = aws_iam_role.deploy.max_session_duration == 3600
    error_message = "Sessions last at most one hour."
  }
}

run "provider_is_github_with_sts_audience" {
  command = apply

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 1 && aws_iam_openid_connect_provider.github[0].url == "https://token.actions.githubusercontent.com"
    error_message = "With no existing provider ARN, the module creates GitHub's provider."
  }

  assert {
    condition     = tolist(aws_iam_openid_connect_provider.github[0].client_id_list) == tolist(["sts.amazonaws.com"])
    error_message = "The only audience is sts.amazonaws.com."
  }

  assert {
    condition     = output.oidc_provider_managed == true
    error_message = "The provider is reported as managed here."
  }
}

# Exact set: one more action, or the right action on a wider resource, reddens.
run "permissions_are_exactly_ecr_push_to_one_repository" {
  command = apply

  assert {
    condition = jsondecode(aws_iam_role_policy.deploy.policy) == {
      Version = "2012-10-17"
      Statement = [
        {
          Sid      = "EcrAuth"
          Effect   = "Allow"
          Action   = "ecr:GetAuthorizationToken"
          Resource = "*"
        },
        {
          Sid    = "PushBackendImage"
          Effect = "Allow"
          Action = [
            "ecr:BatchCheckLayerAvailability",
            "ecr:InitiateLayerUpload",
            "ecr:UploadLayerPart",
            "ecr:CompleteLayerUpload",
            "ecr:PutImage",
            "ecr:BatchGetImage",
            "ecr:DescribeImages",
          ]
          Resource = "arn:aws:ecr:ap-southeast-1:111122223333:repository/shiftmind-test-backend"
        },
      ]
    }
    error_message = "The deploy role may only authenticate to ECR and push to the backend repository."
  }

  assert {
    condition     = aws_iam_role_policy.deploy.role == aws_iam_role.deploy.id
    error_message = "The policy attaches to the deploy role."
  }
}

run "an_existing_provider_is_looked_up_not_managed" {
  command = apply

  variables {
    github_oidc_provider_arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
  }

  override_data {
    target = data.aws_iam_openid_connect_provider.existing[0]
    values = {
      arn = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    }
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0 && output.oidc_provider_managed == false
    error_message = "With an existing provider ARN, no provider resource may exist (a teardown must not delete it)."
  }

  assert {
    condition     = jsondecode(aws_iam_role.deploy.assume_role_policy).Statement[0].Principal.Federated == "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
    error_message = "The role trusts the looked-up provider."
  }
}

run "a_wildcard_repository_is_rejected" {
  command = plan

  variables {
    github_repository = "example-owner/*"
  }

  expect_failures = [var.github_repository]
}

run "a_wildcard_environment_is_rejected" {
  command = plan

  variables {
    github_environment = "*"
  }

  expect_failures = [var.github_environment]
}
