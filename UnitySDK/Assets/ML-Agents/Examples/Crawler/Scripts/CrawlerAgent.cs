﻿using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using MLAgents;

[RequireComponent(typeof(JointDriveController))] // Required to set joint forces
public class CrawlerAgent : Agent
{
    [Header("Target To Walk Towards")] [Space(10)]
    public Transform target;

    public Transform ground;
    public bool detectTargets;
    public bool respawnTargetWhenTouched;
    public float targetSpawnRadius;

    [Header("Body Parts")] [Space(10)] public Transform body;
    public Transform leg0Upper;
    public Transform leg0Lower;
    public Transform leg1Upper;
    public Transform leg1Lower;
    public Transform leg2Upper;
    public Transform leg2Lower;
    public Transform leg3Upper;
    public Transform leg3Lower;

    private Transform[] body_parts;
    private Transform[] upper_legs;
    private Transform[] lower_legs;

    [Header("Joint Settings")] [Space(10)] JointDriveController jdController;
    Vector3 dirToTarget;
    float movingTowardsDot;
    float facingDot;

    [Header("Reward Functions To Use")] [Space(10)]
    public bool rewardMovingTowardsTarget; // Agent should move towards target

    public bool rewardFacingTarget; // Agent should face the target
    public bool rewardUseTimePenalty; // Hurry up

    [Header("Foot Grounded Visualization")] [Space(10)]
    public bool useFootGroundedVisualization;

    public MeshRenderer foot0;
    public MeshRenderer foot1;
    public MeshRenderer foot2;
    public MeshRenderer foot3;
    public Material groundedMaterial;
    public Material unGroundedMaterial;
    bool isNewDecisionStep;
    int currentDecisionStep;

    private ResetParameters resetParams;

    public Vector3 moveJointTest;
    public bool generateNewLegSizes;

    public override void InitializeAgent()
    {
        jdController = GetComponent<JointDriveController>();
        currentDecisionStep = 1;
        var academy = Object.FindObjectOfType<Academy>() as Academy;
        resetParams = academy.resetParameters;
        body_parts =  new Transform[9] { body, leg0Upper, leg0Lower, leg1Upper, leg1Lower, leg2Upper, leg2Lower, leg3Upper, leg3Lower };
        upper_legs = new Transform[4] { leg0Upper, leg1Upper, leg2Upper, leg3Upper };
        lower_legs = new Transform[4] { leg0Lower, leg1Lower, leg2Lower, leg3Lower };

        SetupBodyParts();

        SetResetParameters();
    }

    /// <summary>
    /// We only need to change the joint settings based on decision freq.
    /// </summary>
    public void IncrementDecisionTimer()
    {
        if (currentDecisionStep == agentParameters.numberOfActionsBetweenDecisions
            || agentParameters.numberOfActionsBetweenDecisions == 1)
        {
            currentDecisionStep = 1;
            isNewDecisionStep = true;
        }
        else
        {
            currentDecisionStep++;
            isNewDecisionStep = false;
        }
    }

    /// <summary>
    /// Add relevant information on each body part to observations.
    /// </summary>
    public void CollectObservationBodyPart(BodyPart bp)
    {
        var rb = bp.rb;
        AddVectorObs(bp.groundContact.touchingGround ? 1 : 0); // Whether the bp touching the ground
        AddVectorObs(rb.velocity);
        AddVectorObs(rb.angularVelocity);

        if (bp.rb.transform != body)
        {
            Vector3 localPosRelToBody = body.InverseTransformPoint(rb.position);
            AddVectorObs(localPosRelToBody);
            AddVectorObs(bp.currentXNormalizedRot); // Current x rot
            AddVectorObs(bp.currentYNormalizedRot); // Current y rot
            AddVectorObs(bp.currentZNormalizedRot); // Current z rot
            AddVectorObs(bp.currentStrength / jdController.maxJointForceLimit);
        }
    }

    public override void CollectObservations()
    {
        jdController.GetCurrentJointForces();
        // Normalize dir vector to help generalize
        AddVectorObs(dirToTarget.normalized);

        // Forward & up to help with orientation
        AddVectorObs(body.transform.position.y);
        AddVectorObs(body.forward);
        AddVectorObs(body.up);
        foreach (var bodyPart in jdController.bodyPartsDict.Values)
        {
            CollectObservationBodyPart(bodyPart);
        }
    }

    /// <summary>
    /// Agent touched the target
    /// </summary>
    public void TouchedTarget()
    {
        AddReward(1f);
        if (respawnTargetWhenTouched)
        {
            GetRandomTargetPos();
        }
    }

    /// <summary>
    /// Moves target to a random position within specified radius.
    /// </summary>
    public void GetRandomTargetPos()
    {
        Vector3 newTargetPos = Random.insideUnitSphere * targetSpawnRadius;
        newTargetPos.y = 5;
        target.position = newTargetPos + ground.position;
    }

    void SetupBodyParts()
    {

        // SetResetParameters();

        //Setup each body part
        jdController.SetupBodyPart(body);
        jdController.SetupBodyPart(leg0Upper);
        jdController.SetupBodyPart(leg0Lower);
        jdController.SetupBodyPart(leg1Upper);
        jdController.SetupBodyPart(leg1Lower);
        jdController.SetupBodyPart(leg2Upper);
        jdController.SetupBodyPart(leg2Lower);
        jdController.SetupBodyPart(leg3Upper);
        jdController.SetupBodyPart(leg3Lower);
    }

    public override void AgentAction(float[] vectorAction, string textAction)
    {
        if (detectTargets)
        {
            foreach (var bodyPart in jdController.bodyPartsDict.Values)
            {
                if (bodyPart.targetContact && !IsDone() && bodyPart.targetContact.touchingTarget)
                {
                    TouchedTarget();
                }
            }
        }

        // Update pos to target
        dirToTarget = target.position - jdController.bodyPartsDict[body].rb.position;

        // If enabled the feet will light up green when the foot is grounded.
        // This is just a visualization and isn't necessary for function
        if (useFootGroundedVisualization)
        {
            foot0.material = jdController.bodyPartsDict[leg0Lower].groundContact.touchingGround
                ? groundedMaterial
                : unGroundedMaterial;
            foot1.material = jdController.bodyPartsDict[leg1Lower].groundContact.touchingGround
                ? groundedMaterial
                : unGroundedMaterial;
            foot2.material = jdController.bodyPartsDict[leg2Lower].groundContact.touchingGround
                ? groundedMaterial
                : unGroundedMaterial;
            foot3.material = jdController.bodyPartsDict[leg3Lower].groundContact.touchingGround
                ? groundedMaterial
                : unGroundedMaterial;
        }

        // Joint update logic only needs to happen when a new decision is made
        if (isNewDecisionStep)
        {
            // The dictionary with all the body parts in it are in the jdController
            var bpDict = jdController.bodyPartsDict;

            int i = -1;
            // Pick a new target joint rotation
            bpDict[leg0Upper].SetJointTargetRotation(vectorAction[++i], vectorAction[++i], 0);
            bpDict[leg1Upper].SetJointTargetRotation(vectorAction[++i], vectorAction[++i], 0);
            bpDict[leg2Upper].SetJointTargetRotation(vectorAction[++i], vectorAction[++i], 0);
            bpDict[leg3Upper].SetJointTargetRotation(vectorAction[++i], vectorAction[++i], 0);
            bpDict[leg0Lower].SetJointTargetRotation(vectorAction[++i], 0, 0);
            bpDict[leg1Lower].SetJointTargetRotation(vectorAction[++i], 0, 0);
            bpDict[leg2Lower].SetJointTargetRotation(vectorAction[++i], 0, 0);
            bpDict[leg3Lower].SetJointTargetRotation(vectorAction[++i], 0, 0);

            // Update joint strength
            bpDict[leg0Upper].SetJointStrength(vectorAction[++i]);
            bpDict[leg1Upper].SetJointStrength(vectorAction[++i]);
            bpDict[leg2Upper].SetJointStrength(vectorAction[++i]);
            bpDict[leg3Upper].SetJointStrength(vectorAction[++i]);
            bpDict[leg0Lower].SetJointStrength(vectorAction[++i]);
            bpDict[leg1Lower].SetJointStrength(vectorAction[++i]);
            bpDict[leg2Lower].SetJointStrength(vectorAction[++i]);
            bpDict[leg3Lower].SetJointStrength(vectorAction[++i]);
        }

        // Set reward for this step according to mixture of the following elements.
        if (rewardMovingTowardsTarget)
        {
            RewardFunctionMovingTowards();
        }

        if (rewardFacingTarget)
        { 
            RewardFunctionFacingTarget();
        }

        if (rewardUseTimePenalty)
        {
            RewardFunctionTimePenalty();
        }

        IncrementDecisionTimer();
    }

    /// <summary>
    /// Reward moving towards target & Penalize moving away from target.
    /// </summary>
    void RewardFunctionMovingTowards()
    {
        movingTowardsDot = Vector3.Dot(jdController.bodyPartsDict[body].rb.velocity, dirToTarget.normalized);
        AddReward(0.03f * movingTowardsDot);
    }

    /// <summary>
    /// Reward facing target & Penalize facing away from target
    /// </summary>
    void RewardFunctionFacingTarget()
    {
        facingDot = Vector3.Dot(dirToTarget.normalized, body.forward);
        AddReward(0.01f * facingDot);
    }

    /// <summary>
    /// Existential penalty for time-contrained tasks.
    /// </summary>
    void RewardFunctionTimePenalty()
    {
        AddReward(-0.001f);
    }

    /// <summary>
    /// Loop over body parts and reset them to initial conditions.
    /// </summary>
    public override void AgentReset()
    {
        if (dirToTarget != Vector3.zero)
        {
            transform.rotation = Quaternion.LookRotation(dirToTarget);
        }

        foreach (var bodyPart in jdController.bodyPartsDict.Values)
        {
            bodyPart.Reset(bodyPart);
        }

        isNewDecisionStep = true;
        currentDecisionStep = 1;
        // SetResetParameters();
    }

    public void SetUpperLegSize()
    {
        float upperLegStartingYScale = lower_legs[0].localScale.y;

        if (generateNewLegSizes)
        {
            //RESET TO STARTING POSE
            foreach (var bodyPart in jdController.bodyPartsDict.Values)
            {
                bodyPart.Reset(bodyPart);
            }
            foreach (var bp in upper_legs)
            {
                //DISCONNECT THE JOINT SO WE CAN MOVE IT
                jdController.bodyPartsDict[bp].joint.connectedBody = null;

                float startingYScale = bp.localScale.y;
                bp.localScale = new Vector3(bp.localScale.x, resetParams["upperlegScale"], bp.localScale.z);
                var changeY = (bp.localScale.y - startingYScale) / 2;
                var deltaChange = changeY / startingYScale; //PERCENT AMOUNT OF THE SCALE THAT CHANGED. MOVE THE POSITION BASED ON THIS DELTA CHANGE
                bp.localPosition = jdController.bodyPartsDict[bp].startingLocalPos + bp.up * deltaChange;

                //RECONNECT THE JOINT TO THE BODY
                jdController.bodyPartsDict[bp].joint.connectedBody = jdController.bodyPartsDict[body].rb;

            }
            for (int i = 0; i < 4; i++)
            {

                var bp = lower_legs[i];

                // CHANGE ANCHOR POSITION?
                jdController.bodyPartsDict[bp].joint.autoConfigureConnectedAnchor = false;

                //set the anchor
                jdController.bodyPartsDict[bp].joint.connectedAnchor = upper_legs[i].gameObject.GetComponentInChildren<Transform>().localPosition;

                //DISCONNECT THE JOINT SO WE CAN MOVE IT
                jdController.bodyPartsDict[bp].joint.connectedBody = null;
                var changeY = (bp.localScale.y - upperLegStartingYScale);
                var deltaChange = changeY / upperLegStartingYScale; //PERCENT AMOUNT OF THE SCALE THAT CHANGED. MOVE THE POSITION BASED ON THIS DELTA CHANGE
                bp.localPosition = (jdController.bodyPartsDict[bp].startingLocalPos + bp.up * deltaChange);

                //RECONNECT THE JOINT TO THE UPPER LEG
                jdController.bodyPartsDict[bp].joint.connectedBody = jdController.bodyPartsDict[upper_legs[i]].rb;

                jdController.bodyPartsDict[bp].joint.autoConfigureConnectedAnchor = true;
            }

            jdController.bodyPartsDict.Clear();
            jdController.bodyPartsList.Clear();
            SetupBodyParts();
        }
    }

    public void SetForeLegSize()
    {

        //foreach (var bp in lower_legs)
        //{
        //    bp.localScale = new Vector3(bp.localScale.x, resetParams["forelegScale"], bp.localScale.z);
        //}
        if (generateNewLegSizes)
        {
            for (int i = 0; i < 4; i++)
            {
                var bp = lower_legs[i];
                var upper_leg_bp = upper_legs[i];

                // CHANGE ANCHOR POSITION?
                jdController.bodyPartsDict[bp].joint.autoConfigureConnectedAnchor = false;
                jdController.bodyPartsDict[bp].joint.connectedBody = null;

                float startingYScale = bp.localScale.y;
                bp.localScale = new Vector3(bp.localScale.x, resetParams["forelegScale"], bp.localScale.z);
                var changeY = (bp.localScale.y - startingYScale) / 2;
                var deltaChange = changeY / startingYScale;
                bp.localPosition = jdController.bodyPartsDict[bp].startingLocalPos + bp.up * deltaChange;
                   
                //RECONNECT THE JOINT TO THE UPPERLEG
                jdController.bodyPartsDict[bp].joint.connectedBody = jdController.bodyPartsDict[upper_leg_bp].rb;

                //jdController.bodyPartsDict[bp].joint.connectedAnchor = upper_leg_bp.transform.GetChild(0).localPosition;
                jdController.bodyPartsDict[bp].joint.connectedAnchor = new Vector3(0f, -1f, 0);
                jdController.bodyPartsDict[bp].joint.autoConfigureConnectedAnchor = true;
            }
        }
        jdController.bodyPartsDict.Clear();
        jdController.bodyPartsList.Clear();
        SetupBodyParts();
    }

    void SetLegSizes()
    {
        SetUpperLegSize();
        SetForeLegSize();
        generateNewLegSizes = false;
    }

    void SetAgentStartingHeight()
    {
        float newHeight = leg0Upper.localScale.y + leg0Lower.localScale.y + 2;

        foreach (var bp in body_parts)
        {
            bp.position = new Vector3(bp.position.x, newHeight, bp.position.z);
        }
    }

    public void SetResetParameters()
    {
        SetAgentStartingHeight();
        SetLegSizes();
    }
}
