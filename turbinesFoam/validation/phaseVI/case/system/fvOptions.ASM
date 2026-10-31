/*--------------------------------*- C++ -*----------------------------------*\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Website:  www.openfoam.com                      |
|   \\  /    A nd           |                                                 |
|    \\/     M anipulation  |                                                 |
\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvOptions;
}
// Generated from config/case.yaml. Do not edit by hand.

turbine
{
    type axialFlowTurbineALSource;
    active on;

    axialFlowTurbineALSourceCoeffs
    {
        fieldNames (U);
        selectionMode cellSet;
        cellSet turbine;
        origin (0 0 12.192);
        axis (-1 0 0);
        verticalDirection (0 0 1);
        freeStreamVelocity (7 0 0);
        tipSpeedRatio 5.408;
        rotorRadius 5.029;
        hubRadius 0.5083;
        azimuthalOffset 0;

        dynamicStall
        {
            active off;
            dynamicStallModel LeishmanBeddoes;
        }

        rotationalAugmentation
        {
            active off;
            model DuSelig;
            a 1;
            b 1;
            d 1;
        }

        endEffects
        {
            active on;
            endEffectsModel Glauert;
            GlauertCoeffs
            {
                tipEffects off;
                rootEffects on;
            }
        }

        tipCorrection
        {
            active on;
            model DagSorensen;
            wakeTurns 2;
            wakeAzimuthalStep 2;
            epsilon 0;
        }

        blades
        {
            blade1
            {
                writePerf true;
                writeElementPerf true;
                elementType actuatorSurfaceElement;
                nChordwise 5;
                nElements 50;
                elementProfiles
                (
                    cylinder cylinder cylinder cylinder cylinder cylinder cylinder cylinder S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809 S809
                );
                elementData
                (
                    (0 0.5083 0 0.218 0.5 -4.815)
                    (0 0.6604 0 0.218 0.5 -4.815)
                    (0 0.8835 0 0.183 0.5 -4.815)
                    (0 1.0085 0 0.349 0.359 -11.515)
                    (0 1.0675 0 0.441 0.335 -14.715)
                    (0 1.1335 0 0.544 0.319 -18.215)
                    (0 1.2575 0 0.737 0.3 -24.855)
                    (0 1.343 0 0.728 0.3 -22.889)
                    (0 1.51 0 0.711 0.3 -19.107)
                    (0 1.648 0 0.697 0.3 -16.724)
                    (0 1.952 0 0.666 0.3 -12.794)
                    (0 2.257 0 0.636 0.3 -10.123)
                    (0 2.343 0 0.627 0.3 -9.53)
                    (0 2.562 0 0.605 0.3 -8.24)
                    (0 2.867 0 0.574 0.3 -6.898)
                    (0 3.172 0 0.543 0.3 -5.965)
                    (0 3.185 0 0.542 0.3 -5.93)
                    (0 3.476 0 0.512 0.3 -5.309)
                    (0 3.781 0 0.482 0.3 -4.8)
                    (0 4.023 0 0.457 0.3 -4.434)
                    (0 4.086 0 0.451 0.3 -4.34)
                    (0 4.391 0 0.42 0.3 -3.895)
                    (0 4.696 0 0.389 0.3 -3.463)
                    (0 4.78 0 0.381 0.3 -3.346)
                    (0 5 0 0.358 0.3 -3.04)
                    (0 5.029 0 0.3551 0.3 -3)
                );
            }
            blade2
            {
                $blade1;
                writePerf false;
                writeElementPerf false;
                azimuthalOffset 180;
            }
        }

        hub
        {
            nElements 4;
            elementProfiles (cylinder);
            elementData
            (
                (0 0.5083 1.0166)
                (0 -0.5083 1.0166)
            );
        }

        profileData
        {
            S809
            {
                Re 1e6;
                liftReCorrExp 0;
                GaussianCoeffs
                {
                    chordFactor 0.25;
                    dragFactor 1.0;
                    meshFactor 1;
                }
                data (#include "../../data/polars/S809_OSU_Re1M_total.dat");
            }
            cylinder { data ((-180 0 1.1 0) (180 0 1.1 0)); }
        }
    }
}
