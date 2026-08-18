"""Audit infrastructure.

Separate stack because it has a different lifecycle from the agent. The agent
will be rebuilt, renamed, and possibly replaced; the record of what it did must
outlive all of that. RETAIN on the table is deliberate — `cdk destroy` on the
agent must not be able to erase its own history.

The access pattern here is the control. The agent's execution role gets
PutItem and nothing else: no UpdateItem, no DeleteItem, no BatchWriteItem. An
agent that can rewrite its own audit trail does not have an audit trail.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class AuditStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.archive = s3.Bucket(
            self,
            "AuditArchive",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            # Object Lock / compliance retention belongs here once Legal sets a
            # retention period. Flagged in docs/open-questions.md.
            removal_policy=cdk.RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=cdk.Duration.days(90),
                        )
                    ]
                )
            ],
        )

        self.table = dynamodb.Table(
            self,
            "AuditTable",
            table_name="frontline-agent-audit",
            partition_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery=True,
            # Stream is enabled so records can be archived to the bucket above.
            # The stream -> S3 delivery itself is NOT wired here; it needs a
            # Firehose or a small forwarder Lambda. Left undone deliberately
            # rather than half-done — see docs/open-questions.md on retention,
            # which has to be decided before the archive format is fixed.
            stream=dynamodb.StreamViewType.NEW_IMAGE,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # Query "every write_external action last month" without scanning.
        self.table.add_global_secondary_index(
            index_name="by-risk",
            partition_key=dynamodb.Attribute(name="risk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
        )
        # Query "everything that touched regulated data" — the question a
        # FERPA review will actually ask.
        self.table.add_global_secondary_index(
            index_name="by-data-class",
            partition_key=dynamodb.Attribute(
                name="data_class", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
        )

        cdk.CfnOutput(self, "AuditTableName", value=self.table.table_name)
        cdk.CfnOutput(self, "AuditArchiveBucket", value=self.archive.bucket_name)
