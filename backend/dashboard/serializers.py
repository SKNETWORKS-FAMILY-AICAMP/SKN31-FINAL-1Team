# dashboard/serializers.py
from rest_framework import serializers


class SummarySerializer(serializers.Serializer):
    totalTasks = serializers.IntegerField()
    inProgress = serializers.IntegerField()
    pendingApproval = serializers.IntegerField()
    done = serializers.IntegerField()
    completionRate = serializers.IntegerField()


class StatusChartItemSerializer(serializers.Serializer):
    code_id = serializers.CharField()
    code_name = serializers.CharField()
    value = serializers.IntegerField()


class WorkloadItemSerializer(serializers.Serializer):
    userId = serializers.IntegerField()
    name = serializers.CharField()
    taskCount = serializers.IntegerField()


class ActivityLogItemSerializer(serializers.Serializer):
    projectId = serializers.IntegerField(allow_null=True)
    projectName = serializers.CharField()
    taskTitle = serializers.CharField()
    status = serializers.CharField()
    statusLabel = serializers.CharField()
    assigneeName = serializers.CharField()
    updatedAt = serializers.CharField(allow_null=True)


class ProjectListItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    totalTasks = serializers.IntegerField()
    doneTasks = serializers.IntegerField()
    progress = serializers.IntegerField()


class DashboardOverviewResponseSerializer(serializers.Serializer):
    summary = SummarySerializer()
    statusChart = StatusChartItemSerializer(many=True)
    workload = WorkloadItemSerializer(many=True)
    activityLog = ActivityLogItemSerializer(many=True)
    projectList = ProjectListItemSerializer(many=True)


# --- Analytics Serializers ---

class WeeklyCompletionItemSerializer(serializers.Serializer):
    date = serializers.CharField()
    count = serializers.IntegerField()


class TeamContributionItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    done = serializers.IntegerField()
    inProgress = serializers.IntegerField()


class ApprovalPassRateSerializer(serializers.Serializer):
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()


class ProjectBurndownItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    remaining = serializers.IntegerField()


class DashboardAnalyticsResponseSerializer(serializers.Serializer):
    weeklyCompletion = WeeklyCompletionItemSerializer(many=True)
    teamContribution = TeamContributionItemSerializer(many=True)
    averageProcessTime = serializers.FloatField()
    approvalPassRate = ApprovalPassRateSerializer()
    projectBurndown = ProjectBurndownItemSerializer(many=True)